"""Resource caps beyond the timeout (issue #21).

A run can write an arbitrarily large artifact or flood stdout. The cap refuses the evidence
rather than truncating it: an over-cap artifact is not stored, never read by a locator, and the
run carries `ARTIFACT_TOO_LARGE` / `CAPTURE_LIMIT_EXCEEDED` — which governs every verdict, so a
caps failure is `UNVERIFIED`, never a `REPRODUCED` from partial bytes or a `DIVERGED`.
"""

from __future__ import annotations

from pathlib import Path
import sys

from plumb.intake.checkout import resolve_local
from plumb.intake.env import EnvBuild
from plumb.run.capture import CaptureCaps, capture_outputs
from plumb.run.causes import ARTIFACT_TOO_LARGE, CAPTURE_LIMIT_EXCEEDED
from plumb.run.entrypoint import EntryPoint
from plumb.run.runner import run_entrypoint

OK_BUILD = EnvBuild(ok=True, policy="best-effort", detail="stub")


def run(tmp_path: Path, program: str):
    root = tmp_path / "proj"
    root.mkdir(parents=True)
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    checkout = resolve_local(root)
    return run_entrypoint(
        checkout, OK_BUILD, EntryPoint(argv=(sys.executable, "-c", program), source="explicit"),
        run_dir=tmp_path / "run",
    )


def writes(relpath: str, payload: str) -> str:
    return (
        "import pathlib\n"
        f"pathlib.Path({relpath!r}).write_text({payload!r})\n"
    )


def json_files(capture) -> list[str]:
    return [a.relpath for a in capture.artifacts if a.kind == "json"]


class TestPerArtifactCap:
    def test_an_oversized_file_is_refused_not_truncated(self, tmp_path: Path) -> None:
        result = run(tmp_path, writes("results.json", "x" * 2000))
        capture = capture_outputs(result, caps=CaptureCaps(max_artifact_bytes=100))
        assert json_files(capture) == []
        assert capture.causes == (ARTIFACT_TOO_LARGE,)
        assert all(len(capture.read(a)) <= 100 for a in capture.artifacts)
        assert b"x" * 1000 not in b"".join(capture.read(a) for a in capture.artifacts)

    def test_a_stream_over_the_cap_is_refused(self, tmp_path: Path) -> None:
        result = run(tmp_path, "import sys\nsys.stdout.write('y' * 200)\n")
        capture = capture_outputs(result, caps=CaptureCaps(max_artifact_bytes=100))
        assert [a.kind for a in capture.artifacts if a.kind == "stdout"] == []
        assert capture.causes == (ARTIFACT_TOO_LARGE,)

    def test_under_the_cap_nothing_changes(self, tmp_path: Path) -> None:
        result = run(tmp_path, writes("results.json", '{"auc": 0.87}'))
        capture = capture_outputs(result, caps=CaptureCaps(max_artifact_bytes=1000))
        assert json_files(capture) == ["results.json"]
        assert capture.causes == ()


class TestTotalCap:
    def test_the_cap_stops_capture_and_names_itself(self, tmp_path: Path) -> None:
        program = writes("a.json", '{"v": 1}') + writes("b.json", '{"v": 2}')
        result = run(tmp_path, program)
        capture = capture_outputs(
            result, caps=CaptureCaps(max_artifact_bytes=1000, max_total_bytes=12)
        )
        assert json_files(capture) == ["a.json"]
        assert capture.causes == (CAPTURE_LIMIT_EXCEEDED,)

    def test_a_capped_run_is_not_silent(self, tmp_path: Path) -> None:
        result = run(tmp_path, writes("big.json", "z" * 200))
        capture = capture_outputs(result, caps=CaptureCaps(max_artifact_bytes=10))
        from plumb.run.causes import NO_ARTIFACT

        assert NO_ARTIFACT not in capture.causes
