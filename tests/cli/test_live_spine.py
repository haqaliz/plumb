"""live-spine: `plumb verify <paper> <repo>` — the live end-to-end path.

Acceptance criteria of `docs/planning/verify-cli/live-spine/spec.md`, written
failing first (the seam was a SPINE_ERROR stub):

1. End-to-end on the synthetic fixture repo (a `main.py` writing a JSON
   artifact), paper and bindings, `--no-env-build` → exit 0, table + `--json`
   correct (`REPRODUCED` where the artifact matches), run recorded in the run
   area under the CLI's work root.
2. Bindings pointing at values the artifact doesn't contain → exit 1, claims
   `UNVERIFIED` (`NO_BINDING`), never `DIVERGED`.
3. A repo that fails to resolve (missing path / bad rev) → exit 1, named cause
   on stderr, no traceback.
4. A repo with no entry point → exit 1, `ENTRYPOINT_MISSING` on stderr, all
   claims `UNVERIFIED` with that cause in the table (run-level cause governs).
5. `--no-env-build` is honored — the real `build_environment` is never
   constructed (the stub path is the only tested path).
6. `--out` writes a bundle that `verify_bundle` accepts (ephemeral key); paper
   included by default, omitted with `--no-paper`.
7. Determinism: two invocations on the same inputs in one process produce
   byte-identical stdout and reuse one deterministic run dir.
8. A zero-claim paper + runnable repo → exit 0, empty verdict table, empty
   `--json` verdicts array.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from plumb.bundle import verify_bundle
from plumb.cli import main
from plumb.cli.live import derive_run_dir
from plumb.extract.pipeline import extract_claims
from plumb.intake.tree import plumb_tree_hash

_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parents[1]
_FIXTURES = _THIS_DIR / "fixtures"

sys.path.insert(0, str(_THIS_DIR.parent / "verify"))
from verify_helpers import bindings_json  # noqa: E402

PAPER = _FIXTURES / "paper.md"
REPO = _FIXTURES / "repo"
BINDINGS = _FIXTURES / "bindings.json"

ACCURACY_ID = "b3b87b2b43490a529cf2ad7662321e46c3b916aaa0ca6ab74f887d31db2b8000"
PRECISION_ID = "3e137a2e267b131b53702683f7e6f2a85625377ddd67a3dcc6d8d3edc1721de5"


@pytest.fixture
def work_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The CLI's work area for one test: per-test tmp, never the real ~/.plumb-runs."""
    root = tmp_path / "plumb-runs"
    monkeypatch.setattr("plumb.cli.live.WORK_ROOT", root)
    return root


def live_argv(*extra: str) -> list[str]:
    return ["verify", str(PAPER), str(REPO), "--bindings", str(BINDINGS),
            "--no-env-build", *extra]


def fixture_claims():
    """The claims the fixture paper extracts, pinned against the fixture bindings."""
    claims, _ = extract_claims(PAPER.read_text(encoding="utf-8"))
    assert [c.id for c in claims] == [ACCURACY_ID, PRECISION_ID]
    assert [c.metric for c in claims] == ["accuracy", "precision"]
    return claims


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


def make_git_repo(root: Path) -> Path:
    """A one-commit local git repo; offline by construction."""
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, timeout=60)
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, timeout=60)
    subprocess.run(
        ["git", "-c", "user.name=Plumb Test", "-c", "user.email=test@plumb.local",
         "commit", "-q", "-m", "one"],
        cwd=root, check=True, timeout=60,
    )
    return root


class TestEndToEndOnTheSyntheticRepo:
    """Acceptance 1: exit 0, table + JSON correct, run recorded in the run area."""

    def test_the_table_and_the_run_area(self, capsys, work_root: Path) -> None:
        code = main(live_argv())
        captured = capsys.readouterr()
        assert code == 0
        assert captured.err == ""
        out = captured.out
        assert "REPRODUCED" in out
        assert "claims: 2  bound: 2" in out
        assert "REPRODUCED: 2  WITHIN-TOLERANCE: 0  DIVERGED: 0  UNVERIFIED: 0" in out
        assert ACCURACY_ID[:23] in out and PRECISION_ID[:23] in out
        assert str(work_root) not in out  # the run dir's absolute path never leaks

        run_dir = derive_run_dir(work_root, plumb_tree_hash(REPO), ("python", "main.py"))
        assert run_dir.is_dir()
        assert any((run_dir / "objects").iterdir())

    def test_the_json_document(self, capsys, work_root: Path) -> None:
        code = main(live_argv("--json"))
        captured = capsys.readouterr()
        assert code == 0
        document = json.loads(captured.out)
        verdicts = {v["claim_id"]: v for v in document["verdicts"]}
        assert set(verdicts) == {ACCURACY_ID, PRECISION_ID}
        assert all(v["verdict"] == "REPRODUCED" for v in verdicts.values())
        assert document["coverage"] == {
            "claims": 2, "bound": 2,
            "by_verdict": {"REPRODUCED": 2, "WITHIN-TOLERANCE": 0, "DIVERGED": 0,
                           "UNVERIFIED": 0},
            "by_cause": {},
        }


class TestUnboundValuesAreNeverDiverged:
    """Acceptance 2: a missing target is `UNVERIFIED: NO_BINDING`, never `DIVERGED`."""

    def test_unverified_with_no_binding(self, tmp_path: Path, capsys,
                                        work_root: Path) -> None:
        claims = fixture_claims()
        bad = tmp_path / "bad-bindings.json"
        bad.write_bytes(bindings_json(
            (claims[0], "results.json", {"kind": "json_pointer", "pointer": "/metrics/nope"}),
            (claims[1], "results.json", {"kind": "json_pointer", "pointer": "/metrics/nope"}),
        ))
        code = main(["verify", str(PAPER), str(REPO), "--bindings", str(bad),
                     "--no-env-build"])
        captured = capsys.readouterr()
        assert code == 1
        out = captured.out
        assert "UNVERIFIED" in out
        assert "NO_BINDING" in out
        assert "DIVERGED: 0" in out  # never a false DIVERGED: the tally proves it
        assert "claims: 2  bound: 0" in out


class TestResolutionFailures:
    """Acceptance 3: named cause on stderr, exit 1, never a traceback."""

    def test_a_missing_repo_path_is_source_not_found(self, tmp_path: Path, capsys,
                                                     work_root: Path) -> None:
        code = main(["verify", str(PAPER), str(tmp_path / "no-such-dir"),
                     "--bindings", str(BINDINGS), "--no-env-build"])
        captured = capsys.readouterr()
        assert code == 1
        assert captured.out == ""
        assert captured.err.startswith("plumb verify: SOURCE_NOT_FOUND: ")
        assert "Traceback" not in captured.err

    def test_a_bad_rev_is_rev_not_found(self, tmp_path: Path, capsys,
                                        work_root: Path) -> None:
        origin = make_git_repo(tmp_path / "origin")
        code = main(["verify", str(PAPER), origin.as_uri(), "--rev", "v999",
                     "--bindings", str(BINDINGS), "--no-env-build"])
        captured = capsys.readouterr()
        assert code == 1
        assert captured.out == ""
        assert captured.err.startswith("plumb verify: REV_NOT_FOUND: ")
        assert "Traceback" not in captured.err


class TestMissingEntryPoint:
    """Acceptance 4: the run-level cause governs — the false-`DIVERGED` guard holds."""

    def test_all_claims_are_unverified_with_the_cause(
        self, tmp_path: Path, capsys, work_root: Path
    ) -> None:
        empty = tmp_path / "empty-repo"
        empty.mkdir()
        (empty / "README.md").write_text("# nothing here\n", encoding="utf-8")
        code = main(["verify", str(PAPER), str(empty), "--bindings", str(BINDINGS),
                     "--no-env-build"])
        captured = capsys.readouterr()
        assert code == 1
        assert captured.err.startswith("plumb verify: ENTRYPOINT_MISSING: ")
        out = captured.out
        assert "UNVERIFIED" in out
        assert "ENTRYPOINT_MISSING" in out
        assert "DIVERGED: 0" in out


class TestNoEnvBuildIsTheOnlyTestedPath:
    """Acceptance 5: the stub path never constructs the real build."""

    def test_the_real_build_is_never_constructed(
        self, monkeypatch: pytest.MonkeyPatch, capsys, work_root: Path
    ) -> None:
        monkeypatch.setattr(
            "plumb.cli.live.build_environment",
            lambda *args, **kwargs: pytest.fail("the real env build must never run in tests"),
        )
        code = main(live_argv())
        captured = capsys.readouterr()
        assert code == 0
        assert "REPRODUCED" in captured.out


class TestOutWritesAVerifyingBundle:
    """Acceptance 6: `--out` builds a bundle that `verify_bundle` accepts."""

    def test_the_bundle_verifies_with_the_paper_included(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
        work_root: Path
    ) -> None:
        key, allowed = make_key(tmp_path / "keys")
        json_out = main(live_argv("--json"))
        assert json_out == 0
        committed = capsys.readouterr().out

        out = tmp_path / "bundle"
        monkeypatch.chdir(_REPO_ROOT)
        code = main(["verify", os.path.relpath(PAPER, _REPO_ROOT),
                     os.path.relpath(REPO, _REPO_ROOT),
                     "--bindings", os.path.relpath(BINDINGS, _REPO_ROOT),
                     "--no-env-build", "--out", str(out), "--signer-key", str(key)])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        assert (out / "paper.md").is_file()
        assert (out / "verdicts.json").read_bytes() == committed.encode("utf-8")

        report = verify_bundle(out, allowed_signers=allowed, principal="plumb-bundle")
        assert report.ok, report.causes
        assert report.manifest["paper"]["source"] == os.path.relpath(PAPER, _REPO_ROOT)
        assert report.manifest["source"]["location"] == os.path.relpath(REPO, _REPO_ROOT)
        environment = (out / "environment.txt").read_text(encoding="utf-8")
        assert "python pin" in environment and "best-effort" in environment

    def test_no_paper_omits_the_paper_and_the_verifier_supplies_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
        work_root: Path
    ) -> None:
        key, allowed = make_key(tmp_path / "keys")
        out = tmp_path / "bundle"
        monkeypatch.chdir(_REPO_ROOT)
        code = main(["verify", os.path.relpath(PAPER, _REPO_ROOT),
                     os.path.relpath(REPO, _REPO_ROOT),
                     "--bindings", os.path.relpath(BINDINGS, _REPO_ROOT),
                     "--no-env-build", "--out", str(out), "--no-paper",
                     "--signer-key", str(key)])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        assert not (out / "paper.md").exists()
        report = verify_bundle(
            out, allowed_signers=allowed, principal="plumb-bundle",
            paper=PAPER.read_bytes(),
        )
        assert report.ok, report.causes


class TestDeterminism:
    """Acceptance 7: same inputs, one process → byte-identical stdout, one run dir."""

    def test_two_invocations_are_byte_identical(self, capsys, work_root: Path) -> None:
        assert main(live_argv()) == 0
        first = capsys.readouterr().out
        assert main(live_argv()) == 0
        second = capsys.readouterr().out
        assert first == second

        runs = [p for p in work_root.iterdir() if p.name.startswith("run-")]
        assert len(runs) == 1  # deterministic naming, not run-1/run-2
        expected = derive_run_dir(work_root, plumb_tree_hash(REPO), ("python", "main.py"))
        assert runs[0] == expected
        assert runs[0].is_dir()


class TestZeroClaimPaper:
    """Acceptance 8: a vacuous paper still runs; empty table, exit 0."""

    def test_the_run_happens_and_the_table_is_empty(
        self, tmp_path: Path, capsys, work_root: Path
    ) -> None:
        paper = tmp_path / "vacuous.md"
        paper.write_text(
            "# Demo Model\n\n## Results\n\nThe model performed well overall.\n",
            encoding="utf-8",
        )
        bindings = tmp_path / "bindings.json"
        bindings.write_text('{"bindings": []}\n', encoding="utf-8")
        code = main(["verify", str(paper), str(REPO), "--bindings", str(bindings),
                     "--no-env-build"])
        captured = capsys.readouterr()
        assert code == 0
        out = captured.out
        assert "claims: 0  bound: 0" in out
        assert "REPRODUCED: 0  WITHIN-TOLERANCE: 0  DIVERGED: 0  UNVERIFIED: 0" in out

        code = main(["verify", str(paper), str(REPO), "--bindings", str(bindings),
                     "--no-env-build", "--json"])
        document = json.loads(capsys.readouterr().out)
        assert code == 0
        assert document["verdicts"] == []