"""Capture and the freshness guard (R3).

`capture_outputs(result)` turns a finished run into content-addressed
artifacts: stdout, stderr, and every `.json`/`.csv` in the run's working copy.
Each fresh artifact's bytes are copied into the run's object store under their
SHA-256, and `Capture.read` is the only way back to them.

**The freshness guard is the load-bearing test here** (`CLAUDE.md` #5:
reproduce what ran, not what was committed). A file whose mtime is strictly
before the run start is a `StaleOutput` — relpath, mtime and size, *never its
bytes* — so it never enters the store and nothing downstream can parse it.
The boundary is strict: a file stamped exactly at the run start is fresh, one
nanosecond earlier is stale. A committed output left untouched, a file the run
back-dates, and a `cp -p` of a committed result are all stale.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys

import pytest

from plumb.intake.checkout import resolve_local
from plumb.intake.env import EnvBuild
from plumb.run.capture import Artifact, StaleOutput, capture_outputs
from plumb.run.causes import NO_ARTIFACT, STALE_ARTIFACT
from plumb.run.entrypoint import EntryPoint
from plumb.run.runner import run_entrypoint

OK_BUILD = EnvBuild(ok=True, policy="best-effort", detail="stub")
COMMITTED = b'{"auc": 0.87, "note": "committed, not produced by this run"}'
OLD = 1_000_000_000  # 2001-09-09, long before any run


def make_checkout(root: Path, files: dict[str, bytes] | None = None):
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in (files or {"README.md": b"# demo\n"}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return resolve_local(root)


def committed_checkout(tmp_path: Path):
    """A checkout carrying a committed result, back-dated like a real clone's."""
    checkout = make_checkout(tmp_path / "proj", {"results/out.json": COMMITTED})
    os.utime(checkout.checkout_dir / "results/out.json", (OLD, OLD))
    return checkout


def run(tmp_path: Path, program: str, *, checkout=None):
    checkout = checkout or make_checkout(tmp_path / "proj")
    entry = EntryPoint(argv=(sys.executable, "-c", program), source="explicit")
    return run_entrypoint(checkout, OK_BUILD, entry, run_dir=tmp_path / "run")


def by_relpath(capture) -> dict[str, Artifact]:
    return {artifact.relpath: artifact for artifact in capture.artifacts}


def stored_blobs(result) -> set[bytes]:
    store = result.run_dir / "objects"
    return {path.read_bytes() for path in store.iterdir()} if store.is_dir() else set()


WRITES_OUTPUTS = (
    "import os; os.makedirs('sub', exist_ok=True); "
    "open('out.json', 'w').write('{\"auc\": 0.91}'); "
    "open('sub/data.csv', 'w').write('metric,value\\nauc,0.91\\n'); "
    "open('notes.txt', 'w').write('not an output'); "
    "print('AUC = 0.91')"
)


class TestContentAddressing:
    def test_stdout_json_and_csv_are_captured_with_hashes(self, tmp_path: Path) -> None:
        result = run(tmp_path, WRITES_OUTPUTS)
        artifacts = by_relpath(capture_outputs(result))
        expected = {
            "<stdout>": ("stdout", b"AUC = 0.91\n"),
            "out.json": ("json", b'{"auc": 0.91}'),
            "sub/data.csv": ("csv", b"metric,value\nauc,0.91\n"),
        }
        for relpath, (kind, data) in expected.items():
            artifact = artifacts[relpath]
            assert artifact.kind == kind
            assert artifact.sha256 == hashlib.sha256(data).hexdigest()
            assert artifact.size == len(data)

    def test_other_files_are_not_outputs(self, tmp_path: Path) -> None:
        artifacts = by_relpath(capture_outputs(run(tmp_path, WRITES_OUTPUTS)))
        assert "notes.txt" not in artifacts

    def test_file_provenance_carries_the_mtime(self, tmp_path: Path) -> None:
        result = run(tmp_path, WRITES_OUTPUTS)
        artifacts = by_relpath(capture_outputs(result))
        assert artifacts["out.json"].mtime_ns >= result.started_at_ns
        assert artifacts["<stdout>"].mtime_ns is None

    def test_artifacts_are_in_a_fixed_order(self, tmp_path: Path) -> None:
        capture = capture_outputs(run(tmp_path, WRITES_OUTPUTS))
        keys = [(a.kind, a.relpath) for a in capture.artifacts]
        assert keys == sorted(keys)

    def test_read_returns_the_stored_bytes(self, tmp_path: Path) -> None:
        result = run(tmp_path, WRITES_OUTPUTS)
        capture = capture_outputs(result)
        artifact = by_relpath(capture)["out.json"]
        # The store holds the bytes as captured; a later edit in the working
        # copy cannot change what C4 reads.
        (result.workdir / "out.json").write_bytes(b'{"auc": 0.99}')
        assert capture.read(artifact) == b'{"auc": 0.91}'
        assert (result.run_dir / "objects" / artifact.sha256).is_file()

    def test_read_refuses_a_tampered_store(self, tmp_path: Path) -> None:
        result = run(tmp_path, WRITES_OUTPUTS)
        capture = capture_outputs(result)
        artifact = by_relpath(capture)["out.json"]
        (result.run_dir / "objects" / artifact.sha256).write_bytes(b'{"auc": 0.99}')
        with pytest.raises(ValueError):
            capture.read(artifact)

    def test_a_symlinked_output_is_not_followed(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.json"
        outside.write_bytes(b'{"secret": 1}')
        result = run(tmp_path, f"import os; os.symlink({str(outside)!r}, 'link.json')")
        assert "link.json" not in by_relpath(capture_outputs(result))
        assert b'{"secret": 1}' not in stored_blobs(result)


class TestTheFreshnessGuard:
    """Load-bearing: a stale output is recorded, and its bytes are never read."""

    def test_an_untouched_committed_output_is_stale_and_never_stored(self, tmp_path: Path) -> None:
        result = run(tmp_path, "print('ran')", checkout=committed_checkout(tmp_path))
        capture = capture_outputs(result)
        assert "results/out.json" not in by_relpath(capture)
        assert capture.stale == (
            StaleOutput(relpath="results/out.json", mtime_ns=OLD * 10**9, size=len(COMMITTED)),
        )
        assert capture.stale[0].cause == STALE_ARTIFACT
        assert COMMITTED not in stored_blobs(result)

    def test_a_file_the_run_back_dates_is_stale(self, tmp_path: Path) -> None:
        result = run(
            tmp_path,
            f"import os; open('out.json', 'w').write('{{}}'); os.utime('out.json', ({OLD}, {OLD}))",
        )
        capture = capture_outputs(result)
        assert [s.relpath for s in capture.stale] == ["out.json"]
        assert "out.json" not in by_relpath(capture)

    def test_a_cp_p_of_a_committed_result_is_stale(self, tmp_path: Path) -> None:
        result = run(
            tmp_path,
            "import shutil; shutil.copy2('results/out.json', 'fresh_looking.json')",
            checkout=committed_checkout(tmp_path),
        )
        capture = capture_outputs(result)
        assert {s.relpath for s in capture.stale} == {"results/out.json", "fresh_looking.json"}
        assert COMMITTED not in stored_blobs(result)

    def test_a_committed_output_the_run_rewrites_is_fresh(self, tmp_path: Path) -> None:
        result = run(
            tmp_path,
            "open('results/out.json', 'w').write('{\"auc\": 0.85}')",
            checkout=committed_checkout(tmp_path),
        )
        capture = capture_outputs(result)
        assert capture.stale == ()
        assert capture.read(by_relpath(capture)["results/out.json"]) == b'{"auc": 0.85}'

    def test_the_boundary_is_strict(self, tmp_path: Path) -> None:
        result = run(tmp_path, "open('at.json', 'w').write('1'); open('before.json', 'w').write('2')")
        start = result.started_at_ns
        os.utime(result.workdir / "at.json", ns=(start, start))
        os.utime(result.workdir / "before.json", ns=(start - 1, start - 1))
        capture = capture_outputs(result)
        assert "at.json" in by_relpath(capture)
        assert [s.relpath for s in capture.stale] == ["before.json"]


class TestNoArtifact:
    def test_a_silent_successful_run_is_no_artifact(self, tmp_path: Path) -> None:
        capture = capture_outputs(run(tmp_path, "pass"))
        assert capture.causes == (NO_ARTIFACT,)

    def test_only_stale_outputs_is_still_no_artifact(self, tmp_path: Path) -> None:
        capture = capture_outputs(run(tmp_path, "pass", checkout=committed_checkout(tmp_path)))
        assert capture.causes == (NO_ARTIFACT,)
        assert len(capture.stale) == 1

    def test_stdout_alone_is_an_artifact(self, tmp_path: Path) -> None:
        assert capture_outputs(run(tmp_path, "print('AUC = 0.91')")).causes == ()

    def test_stderr_alone_is_still_no_artifact(self, tmp_path: Path) -> None:
        capture = capture_outputs(run(tmp_path, "import sys; sys.stderr.write('warn')"))
        assert capture.causes == (NO_ARTIFACT,)

    def test_a_failed_run_is_not_no_artifact(self, tmp_path: Path) -> None:
        # The run's own failure (WONT_RUN) governs; NO_ARTIFACT is a binding
        # problem for a run that succeeded.
        result = run(tmp_path, "import sys; sys.exit(1)")
        assert result.failure is not None
        assert capture_outputs(result).causes == ()


class TestStderrIsDiagnosticOnly:
    def test_stderr_is_captured_but_not_locatable(self, tmp_path: Path) -> None:
        capture = capture_outputs(run(tmp_path, "import sys; print('out'); sys.stderr.write('err')"))
        stderr = by_relpath(capture)["<stderr>"]
        assert stderr.diagnostic_only
        assert capture.read(stderr) == b"err"
        assert stderr not in capture.locatable
        assert {a.relpath for a in capture.locatable} == {"<stdout>"}
