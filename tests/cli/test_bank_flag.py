"""verify --bank: the verify-to-corpus loop (cross-paper-coverage, Phase 3).

`docs/planning/cross-paper-coverage/bank-flag/plan_20261002.md`, Phase 3,
written failing first: `plumb verify --bank` banks the run's record into the
default store `corpus/local` (the same default `corpus bank`/`corpus report`
use) through the same `bank_record` seam — replay-chain validation, write-once
no-op. The verdicts render regardless of the bank's outcome; a refusal is the
named cause `CORPUS_REFUSED` (or `RECORD_INVALID`) on stderr with exit 1;
success prints the case id; the record dir is discarded after banking.

1. A live run with `--bank` banks a case under the default store (redirected
   into the test by the cwd), prints `banked <case_id>` after the verdicts,
   and exits 0. The case carries no local path.
2. `--from-record --bank` on the AgroDesign fixture banks the same
   content-addressed case `corpus bank --store` produces for the same record;
   a second run is a no-op — `already banked`, exit 0, case bytes untouched.
3. A `NO_ARTIFACT` run (a repo whose entry writes nothing) banks too: exit 1,
   every claim `UNVERIFIED`, the run-level cause visible in the banked case's
   trace.json — the honest default, never a refusal.
4. A bank refusal (the store path is a regular file) is `CORPUS_REFUSED` on
   stderr with exit 1 — the verdicts still rendered on stdout first.
5. `--bank` with `--out` (ephemeral signer key) writes both the signed bundle
   and the case.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from plumb.bundle import verify_bundle
from plumb.cli import CORPUS_REFUSED, main
from plumb.corpus import read_case

_THIS_DIR = Path(__file__).parent
_GATE_DIR = _THIS_DIR.parent / "gate"

sys.path.insert(0, str(_GATE_DIR))
from test_agrodesign_fixture import FIXTURE  # noqa: E402

PAPER = _THIS_DIR / "fixtures" / "paper.md"
REPO = _THIS_DIR / "fixtures" / "repo"
BINDINGS = _THIS_DIR / "fixtures" / "bindings.json"


@pytest.fixture
def work_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The CLI's work area for one test: per-test tmp, never the real ~/.plumb-runs."""
    root = tmp_path / "plumb-runs"
    monkeypatch.setattr("plumb.cli.live.WORK_ROOT", root)
    return root


@pytest.fixture
def default_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The default store `corpus/local`, redirected into the test via the cwd."""
    monkeypatch.chdir(tmp_path)
    return tmp_path / "corpus" / "local"


def live_argv(*extra: str) -> list[str]:
    return ["verify", str(PAPER), str(REPO), "--bindings", str(BINDINGS),
            "--no-env-build", *extra]


def make_key(directory: Path) -> tuple[Path, Path]:
    """An ephemeral Ed25519 key and allowed-signers naming `plumb-bundle`."""
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


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under `root`, as a posix-relative path -> bytes snapshot."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _banked_case_id(out: str) -> str:
    """The case id the `banked <case_id>` line on stdout names."""
    return out.rsplit("banked ", 1)[1].strip()


class TestALiveRunBanks:
    """Acceptance 1: `--bank` banks the live run's record into the default store."""

    def test_the_case_exists_under_the_default_store(
        self, tmp_path: Path, capsys, work_root: Path, default_store: Path
    ) -> None:
        code = main(live_argv("--bank", "--json"))
        captured = capsys.readouterr()
        assert code == 0
        assert captured.err == ""
        out = captured.out
        assert out.endswith(f"banked {_banked_case_id(out)}\n")
        json_text = out[: out.index("banked")]
        document = json.loads(json_text)  # the verdicts document is whole before the line
        assert document["coverage"]["bound"] == 2

        case_id = _banked_case_id(out)
        case_dir = default_store / case_id
        assert (case_dir / "case.json").is_file()
        case = read_case(case_dir)
        assert case.case.case_id == case_id
        assert case.members["verdicts"] == json_text.encode("utf-8")

    def test_the_banked_case_carries_no_local_path(
        self, tmp_path: Path, capsys, work_root: Path, default_store: Path
    ) -> None:
        code = main(live_argv("--bank"))
        assert code == 0
        case_id = _banked_case_id(capsys.readouterr().out)
        case_dir = default_store / case_id
        for path in case_dir.rglob("*"):
            if path.is_file() and path.suffix != ".pdf":
                text = path.read_bytes().decode("utf-8", "replace")
                assert str(tmp_path) not in text, f"{path.name} carries a temp path"


class TestFromRecordBanksTheSameCase:
    """Acceptance 2: `--from-record --bank` banks what `corpus bank` would bank."""

    def test_the_case_id_matches_the_corpus_bank_case_id(
        self, tmp_path: Path, capsys, default_store: Path
    ) -> None:
        code = main(["verify", "--from-record", str(FIXTURE), "--bank"])
        captured = capsys.readouterr()
        assert code == 0
        out = captured.out
        assert "REPRODUCED" in out
        assert captured.err == ""
        case_id = _banked_case_id(out)
        assert (default_store / case_id / "case.json").is_file()

        other = tmp_path / "elsewhere"
        assert main(["corpus", "bank", str(FIXTURE), "--store", str(other)]) == 0
        assert capsys.readouterr().out == f"banked {case_id}\n"
        assert (other / case_id).is_dir()

    def test_a_second_bank_is_a_no_op(
        self, tmp_path: Path, capsys, default_store: Path
    ) -> None:
        assert main(["verify", "--from-record", str(FIXTURE), "--bank"]) == 0
        case_id = _banked_case_id(capsys.readouterr().out)
        snapshot = _tree_bytes(default_store)

        code = main(["verify", "--from-record", str(FIXTURE), "--bank"])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.out.endswith(f"already banked: {case_id}\n")
        assert captured.err == ""
        assert _tree_bytes(default_store) == snapshot


class TestANoArtifactRunStillBanks:
    """Acceptance 3: a silent run banks an all-UNVERIFIED case, never a refusal."""

    def test_the_case_banks_with_the_run_level_cause(
        self, tmp_path: Path, capsys, work_root: Path, default_store: Path
    ) -> None:
        silent = tmp_path / "silent-repo"
        silent.mkdir()
        (silent / "main.py").write_text("", encoding="utf-8")
        code = main(["verify", str(PAPER), str(silent), "--bindings", str(BINDINGS),
                     "--no-env-build", "--bank"])
        captured = capsys.readouterr()
        assert code == 1
        assert captured.err.startswith("plumb verify: NO_ARTIFACT: ")
        out = captured.out
        assert "claims: 2  bound: 0" in out
        assert "UNVERIFIED: 2" in out

        case_id = _banked_case_id(out)
        case_dir = default_store / case_id
        assert (case_dir / "case.json").is_file()
        trace = json.loads((case_dir / "trace.json").read_bytes())
        assert trace["causes"] == ["NO_ARTIFACT"]
        verdicts = json.loads((case_dir / "verdicts.json").read_bytes())
        assert [v["verdict"] for v in verdicts["verdicts"]] == ["UNVERIFIED", "UNVERIFIED"]


class TestABankRefusalIsCorpusRefused:
    """Acceptance 4: a store that refuses is a named cause; the verdicts still render."""

    def test_the_store_as_a_file_refuses_with_the_verdicts_first(
        self, tmp_path: Path, capsys, work_root: Path, default_store: Path
    ) -> None:
        default_store.parent.mkdir()
        default_store.write_text("not a directory\n", encoding="utf-8")
        code = main(live_argv("--bank"))
        captured = capsys.readouterr()
        assert code == 1
        assert captured.err.startswith(f"plumb verify: {CORPUS_REFUSED}: ")
        assert "Traceback" not in captured.err
        assert "REPRODUCED" in captured.out  # the table rendered before the failure line
        assert "banked" not in captured.out


class TestBankWithOutWritesBoth:
    """Acceptance 5: `--bank` with `--out` writes the bundle and the case."""

    def test_the_bundle_verifies_and_the_case_banks(
        self, tmp_path: Path, capsys, work_root: Path, default_store: Path
    ) -> None:
        # The bundle refuses local paths, so the inputs must be bare names in the
        # (cwd-redirected) test directory, exactly as a user's own inputs would be.
        shutil.copyfile(PAPER, tmp_path / "paper.md")
        shutil.copyfile(BINDINGS, tmp_path / "bindings.json")
        shutil.copytree(REPO, tmp_path / "repo")
        key, allowed = make_key(tmp_path / "keys")
        out = tmp_path / "bundle"
        code = main(["verify", "paper.md", "repo", "--bindings", "bindings.json",
                     "--no-env-build", "--bank", "--out", str(out),
                     "--signer-key", str(key)])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        report = verify_bundle(out, allowed_signers=allowed, principal="plumb-bundle")
        assert report.ok, report.causes
        case_id = _banked_case_id(captured.out)
        assert (default_store / case_id / "case.json").is_file()