"""replay: `plumb verify --from-record <dir>` — offline replay through the C4 seam.

Acceptance criteria of `docs/planning/verify-cli/replay/spec.md`, written failing
first (the seam was a SPINE_ERROR stub):

1. `--from-record fixtures/gate/agrodesign/ --json` exits 0 and its stdout is
   byte-identical to the committed `verdicts.json` (86 claims, 85 REPRODUCED /
   1 DIVERGED — the byte equality carries the tally).
2. `--from-record` with live-mode arguments exits 2 (usage) — already pinned by
   cli-core (`tests/cli/test_cli_core.py::test_from_record_rejects_live_arguments`);
   not duplicated here.
3. A tampered record (a trace id that no longer matches, or an object that is not
   its hash) is `RECORD_INVALID`, exit 1, never a traceback, never a wrong verdict.
4. A record missing any required member is `RECORD_INVALID` naming the member.
5. `--out` rebuilds a signed bundle that `verify_bundle` accepts, with the record's
   run id and tree hash and verdicts equal to the record's.
6. Two `--from-record` invocations under different `PYTHONHASHSEED` produce
   byte-identical stdout.
7. Exit 0 when every claim is decided; exit 1 when any claim is `UNVERIFIED`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from plumb.bundle import verify_bundle
from plumb.cli import RECORD_INVALID, main
from plumb.run import parse_trace

_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parents[1]
_GATE_DIR = _THIS_DIR.parent / "gate"

sys.path.insert(0, str(_GATE_DIR))
from test_agrodesign_fixture import FIXTURE  # noqa: E402

GATE = FIXTURE

#: The members replay requires of a record, named as the error names them.
REQUIRED_MEMBERS = ("claims.json", "bindings.json", "trace.json", "objects", "paper.pdf")


def run_cli(*argv: str, hash_seed: str | None = None) -> subprocess.CompletedProcess[bytes]:
    """The real `plumb` console script in a fresh interpreter; stdout stays bytes."""
    env = os.environ.copy()
    if hash_seed is not None:
        env["PYTHONHASHSEED"] = hash_seed
    return subprocess.run(
        ["uv", "run", "plumb", *argv],
        cwd=_REPO_ROOT, env=env, capture_output=True, timeout=300,
    )


def copy_record(
    tmp_path: Path,
    *,
    drop: tuple[str, ...] = (),
    tamper: str | None = None,
    unbound: bool = False,
) -> Path:
    """A fresh copy of the gate record, minus `drop` or with `tamper` applied.

    `tamper="run_id"` rewrites the recorded run id so `parse_trace` must refuse it;
    `tamper="object"` flips a byte in the object store so `Capture.read` must refuse
    it. `unbound=True` renames every artifact relpath in the trace (relpaths are not
    part of the run id) so no binding finds a target — a clean `UNVERIFIED`.
    """
    rec = tmp_path / "record"
    shutil.copytree(GATE, rec)
    for name in drop:
        path = rec / name
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    if tamper == "run_id":
        trace = json.loads((rec / "trace.json").read_text(encoding="utf-8"))
        trace["run_id"] = "0" * 64
        (rec / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
    elif tamper == "object":
        sha = next(p.name for p in (rec / "objects").iterdir())
        data = bytearray((rec / "objects" / sha).read_bytes())
        data[0] ^= 0x01
        (rec / "objects" / sha).write_bytes(bytes(data))
    elif unbound:
        trace = json.loads((rec / "trace.json").read_text(encoding="utf-8"))
        for artifact in trace["artifacts"]:
            artifact["relpath"] = artifact["relpath"] + ".renamed"
        (rec / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
    return rec


def make_key(directory: Path) -> tuple[Path, Path]:
    """An ephemeral Ed25519 key and allowed-signers naming principal `plumb-bundle`.

    Same pattern as `tests/bundle/conftest.py::make_key` (ssh-keygen, local, no
    network); the principal must be the CLI's `plumb-bundle`, not the bundle tests'
    `plumb-test`.
    """
    directory.mkdir()
    key = directory / "signer"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "plumb-bundle", "-f", str(key)],
        check=True, capture_output=True,
    )
    allowed = directory / "allowed_signers"
    allowed.write_text(
        f"plumb-bundle {(directory / 'signer.pub').read_text().strip()}\n", encoding="utf-8"
    )
    return key, allowed


class TestFromRecordReplaysTheCommittedRecord:
    """Acceptance 1: exit 0, stdout byte-identical to the committed record."""

    def test_json_is_byte_identical_to_the_committed_verdicts(self) -> None:
        result = run_cli("verify", "--from-record", str(GATE), "--json")
        assert result.returncode == 0
        assert result.stdout == (GATE / "verdicts.json").read_bytes()

    def test_the_table_renders_the_gate_panel(self) -> None:
        result = run_cli("verify", "--from-record", str(GATE))
        assert result.returncode == 0
        out = result.stdout.decode("utf-8")
        assert "claims: 86  bound: 86" in out
        assert "REPRODUCED: 85  WITHIN-TOLERANCE: 0  DIVERGED: 1  UNVERIFIED: 0" in out


class TestTamperedRecords:
    """Acceptance 3: `RECORD_INVALID`, never a traceback, never a wrong verdict."""

    @pytest.mark.parametrize(
        "tamper", ["run_id", "object"], ids=("trace-run-id", "object-bytes")
    )
    def test_a_tampered_record_is_record_invalid(
        self, tmp_path: Path, capsys, tamper: str
    ) -> None:
        rec = copy_record(tmp_path, tamper=tamper)
        code = main(["verify", "--from-record", str(rec)])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {RECORD_INVALID}: ")


class TestMissingMembers:
    """Acceptance 4: `RECORD_INVALID` naming the missing member."""

    @pytest.mark.parametrize("member", REQUIRED_MEMBERS)
    def test_each_required_member_is_named(self, tmp_path: Path, capsys, member: str) -> None:
        rec = copy_record(tmp_path, drop=(member,))
        code = main(["verify", "--from-record", str(rec)])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {RECORD_INVALID}: ")
        assert member in captured.err


class TestOutRebuildsABundle:
    """Acceptance 5: `--out` writes a bundle that `verify_bundle` accepts."""

    def test_the_rebuilt_bundle_verifies_and_matches_the_record(
        self, tmp_path: Path, capsys
    ) -> None:
        key, allowed = make_key(tmp_path / "keys")
        out = tmp_path / "bundle"
        code = main(
            ["verify", "--from-record", str(GATE), "--out", str(out), "--signer-key", str(key)]
        )
        assert code == 0
        report = verify_bundle(out, allowed_signers=allowed, principal="plumb-bundle")
        assert report.ok, report.causes
        manifest = report.manifest
        trace = parse_trace((GATE / "trace.json").read_bytes())
        assert manifest["run_id"] == trace.run_id
        assert manifest["tree_hash"] == {
            "scheme": trace.tree_hash.scheme, "digest": trace.tree_hash.digest,
        }
        assert (out / "verdicts.json").read_bytes() == (GATE / "verdicts.json").read_bytes()
        assert (out / "paper.pdf").is_file()

    def test_no_paper_omits_the_paper(self, tmp_path: Path, capsys) -> None:
        key, allowed = make_key(tmp_path / "keys")
        out = tmp_path / "bundle"
        code = main(
            ["verify", "--from-record", str(GATE), "--out", str(out), "--no-paper",
             "--signer-key", str(key)]
        )
        assert code == 0
        assert not (out / "paper.pdf").exists()
        report = verify_bundle(
            out, allowed_signers=allowed, principal="plumb-bundle",
            paper=(GATE / "paper.pdf").read_bytes(),
        )
        assert report.ok, report.causes


class TestCrossProcessByteIdentity:
    """Acceptance 6: byte-identical stdout under different `PYTHONHASHSEED`."""

    def test_json_stdout_is_identical_across_seeds(self) -> None:
        outputs = {}
        for seed in ("0", "1"):
            result = run_cli("verify", "--from-record", str(GATE), "--json", hash_seed=seed)
            assert result.returncode == 0
            outputs[seed] = result.stdout
        assert len(set(outputs.values())) == 1
        assert outputs["0"] == (GATE / "verdicts.json").read_bytes()


class TestExitCodeContract:
    """Acceptance 7: 0 iff every claim decided; 1 when any is `UNVERIFIED`."""

    def test_the_gate_record_exits_zero(self, capsys) -> None:
        assert main(["verify", "--from-record", str(GATE)]) == 0
        capsys.readouterr()

    def test_a_record_with_unverified_claims_exits_one(self, tmp_path: Path, capsys) -> None:
        rec = copy_record(tmp_path, drop=("verdicts.json",), unbound=True)
        code = main(["verify", "--from-record", str(rec)])
        assert code == 1
        out = capsys.readouterr().out
        assert "UNVERIFIED" in out  # the table is the evidence; the exit code is the signal