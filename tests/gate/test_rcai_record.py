"""Offline replay of the RCAI gate verdicts (notebook-paper G3, PRD P5).

`tools/rcai_run.py` ran the paper's own notebook once, at dev time, through the real spine
and committed what C4 needs to decide: the trace, the locatable captured artifacts (by
SHA-256), and the verdicts. This test re-derives every verdict from those committed bytes
alone — no network, no environment, no run — and asserts the CLI's `--from-record --json`
output is byte-identical to `verdicts.json`. The exit code is 1: one claim is `UNVERIFIED`
(`NO_BINDING`, the pre-registered KAA prose statistic), which is the CLI's honest contract —
identity is proven by the bytes, never by the exit code.

The record's invariants are pinned here: `objects/` is exactly the trace's locatable
artifacts under their own hashes (the diagnostic stderr artifact is never committed, and
`objects/` is excluded from the local-path scan because it is raw captured bytes), no
committed member outside `objects/` carries a local path, and replay writes nothing — the
committed record is read-only evidence.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess

from plumb.cli import main
from plumb.run import parse_trace

_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parents[1]
FIXTURE = _REPO_ROOT / "fixtures" / "gate" / "rcai"

#: The same markers the AgroDesign record pins; `/Users/` and `/private/` cover the
#: macOS home and tmp paths this record was produced under.
LOCAL_PATH_MARKERS = ("/Users/", "/home/", "/private/", "/tmp/", "/var/folders/", "C:\\")


def run_cli(*argv: str, hash_seed: str | None = None) -> subprocess.CompletedProcess[bytes]:
    """The real `plumb` console script in a fresh interpreter; stdout stays bytes."""
    env = os.environ.copy()
    if hash_seed is not None:
        env["PYTHONHASHSEED"] = hash_seed
    return subprocess.run(
        ["uv", "run", "plumb", *argv],
        cwd=_REPO_ROOT, env=env, capture_output=True, timeout=300,
    )


def tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under `root`, as a posix-relative path -> bytes snapshot."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


class TestFromRecordReplaysTheCommittedRecord:
    """G3: `--from-record --json` output is byte-identical to the committed verdicts."""

    def test_json_is_byte_identical_to_the_committed_verdicts(self) -> None:
        result = run_cli("verify", "--from-record", str(FIXTURE), "--json")
        assert result.returncode in (0, 1)  # 1: the honest UNVERIFIED contract
        assert result.stderr == b""
        assert result.stdout == (FIXTURE / "verdicts.json").read_bytes()

    def test_the_table_renders_the_campaign_tally(self) -> None:
        result = run_cli("verify", "--from-record", str(FIXTURE))
        assert result.returncode in (0, 1)
        out = result.stdout.decode("utf-8")
        assert "claims: 31  bound: 30" in out
        assert "REPRODUCED: 30  WITHIN-TOLERANCE: 0  DIVERGED: 0  UNVERIFIED: 1" in out


class TestCrossProcessByteIdentity:
    """G5: byte-identical stdout under different `PYTHONHASHSEED`."""

    def test_json_stdout_is_identical_across_seeds(self) -> None:
        outputs = {}
        for seed in ("0", "1"):
            result = run_cli("verify", "--from-record", str(FIXTURE), "--json", hash_seed=seed)
            assert result.returncode in (0, 1)
            outputs[seed] = result.stdout
        assert len(set(outputs.values())) == 1
        assert outputs["0"] == (FIXTURE / "verdicts.json").read_bytes()


class TestObjectsAreTheLocatableArtifactsOnly:
    """The committed object store is exactly the locatable capture, under its own hashes."""

    def test_objects_are_exactly_the_locatable_artifacts(self) -> None:
        trace = parse_trace((FIXTURE / "trace.json").read_bytes())
        locatable = {a.sha256 for a in trace.artifacts if not a.diagnostic_only}
        committed = {p.name for p in (FIXTURE / "objects").iterdir()}
        assert committed == locatable

    def test_every_committed_object_is_its_own_hash(self) -> None:
        for path in (FIXTURE / "objects").iterdir():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == path.name

    def test_the_diagnostic_stderr_is_not_committed(self) -> None:
        trace = parse_trace((FIXTURE / "trace.json").read_bytes())
        (stderr,) = [a for a in trace.artifacts if a.diagnostic_only]
        assert stderr.kind == "stderr"
        assert not (FIXTURE / "objects" / stderr.sha256).exists()


class TestNoLocalPathInCommittedRecordBytes:
    """The no-egress invariant: no member outside the raw capture names this machine."""

    def test_no_committed_member_carries_a_local_path(self) -> None:
        for path in FIXTURE.rglob("*"):
            if path.is_file() and path.parent.name != "objects":
                data = path.read_bytes()
                for marker in LOCAL_PATH_MARKERS:
                    assert marker.encode() not in data, f"{path.name} contains {marker}"


class TestReplayWritesNothing:
    """The replay seam is read-only: the record is evidence, never mutated."""

    def test_replay_leaves_the_record_and_the_cwd_untouched(
        self, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        record = tmp_path / "record"
        shutil.copytree(FIXTURE, record)
        monkeypatch.chdir(tmp_path)
        before = tree_bytes(tmp_path)
        code = main(["verify", "--from-record", str(record), "--json"])
        capsys.readouterr()
        assert code == 1
        assert tree_bytes(tmp_path) == before
