"""The public seam: the run API surface and its named-cause contract (R4).

`plumb.run` is the boundary C4 consumes. This pins what it exposes — entry
point resolution, the runner, capture, the trace, and `run_and_capture` which
chains them — so a rename or a dropped export is a test failure. The cause
vocabulary is pinned too: every name is documented in the module docstring
with its future `UNVERIFIED` mapping.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

import plumb.intake as intake
import plumb.run as run

CAUSE_NAMES = (
    "ENTRYPOINT_MISSING",
    "ENTRYPOINT_AMBIGUOUS",
    "ENV_BUILD_FAILED",
    "WONT_RUN",
    "TIMEOUT",
    "STALE_ARTIFACT",
    "NO_ARTIFACT",
)


class TestThePublicApiSurface:
    def test_the_functions_are_exposed(self) -> None:
        for name in (
            "resolve_entrypoint",
            "run_entrypoint",
            "capture_outputs",
            "build_trace",
            "derive_run_id",
            "serialize_trace",
            "run_and_capture",
        ):
            assert callable(getattr(run, name)), name

    def test_the_records_are_exposed(self) -> None:
        for name in ("EntryPoint", "RunResult", "RunFailure", "Artifact", "StaleOutput", "Capture", "RunTrace"):
            assert hasattr(run, name), name

    def test_the_causes_are_exposed(self) -> None:
        assert issubclass(run.EntryPointMissing, RuntimeError)
        assert issubclass(run.EntryPointAmbiguous, RuntimeError)
        for name in ("WONT_RUN", "TIMEOUT", "STALE_ARTIFACT", "NO_ARTIFACT"):
            assert getattr(run, name) == name


class TestTheNamedCauseVocabulary:
    def test_the_module_docstring_documents_the_unverified_mapping(self) -> None:
        doc = run.__doc__ or ""
        for name in CAUSE_NAMES:
            assert name in doc, name
        assert "UNVERIFIED" in doc


class TestSeamSmoke:
    def test_intake_to_trace_end_to_end(self, tmp_path: Path) -> None:
        repo = tmp_path / "proj"
        (repo / "results").mkdir(parents=True)
        (repo / "main.py").write_bytes(
            b"import json\njson.dump({'auc': 0.91}, open('results/fresh.json', 'w'))\n"
            b"print('AUC = 0.91')\n"
        )
        (repo / "results" / "committed.json").write_bytes(b'{"auc": 0.87}')
        os.utime(repo / "results" / "committed.json", (1_000_000_000, 1_000_000_000))

        checkout = intake.resolve_local(repo)
        descriptor = intake.describe_environment(checkout, tool_versions={})
        build = intake.build_environment(
            checkout, descriptor,
            runner=lambda c, d: intake.EnvBuild(ok=True, policy=d.policy, detail="stub"),
        )
        entry = run.resolve_entrypoint(checkout, descriptor.manifests)
        assert entry.argv == ("python", "main.py")

        # Run the discovered script under this interpreter; `python` on PATH
        # is not guaranteed on every machine that runs the suite.
        explicit = run.EntryPoint(argv=(sys.executable, "main.py"), source=entry.source)
        trace, capture = run.run_and_capture(
            checkout, build, explicit, run_dir=tmp_path / "run"
        )
        assert trace.failure is None
        assert trace.entrypoint_source == "main.py"
        assert {a.relpath for a in capture.locatable} == {"<stdout>", "results/fresh.json"}
        assert [s.relpath for s in trace.stale] == ["results/committed.json"]
        fresh = next(a for a in capture.locatable if a.relpath == "results/fresh.json")
        assert capture.read(fresh) == b'{"auc": 0.91}'
        assert run.serialize_trace(trace).endswith(b"\n")
