"""C3 execution & result capture: run the repo's own entry point.

The public seam of the run package. Four slices land here: entry-point
resolution (`entrypoint.py`), the runner (`runner.py`), content-addressed
capture with the freshness guard (`capture.py`), and the deterministic
`RunTrace` record (`trace.py`). `run_and_capture` chains the last three.

**Nothing here emits a verdict.** A run produces a trace — what ran on which
tree, how it ended, and the content-addressed outputs it wrote — which C4
binds claims against. C3 never decides `REPRODUCED`/`DIVERGED`/`UNVERIFIED`;
it supplies the evidence and the named causes.

**Reproduce what ran, not what was committed** (`CLAUDE.md` #5). The run
works in a copy of the checkout under its run area (mtimes preserved), and an
output whose mtime predates the run start is recorded as stale and never
read. Fresh outputs are read only through the run's object store, by hash.

**Named failure causes** — every failure resolves to one of these, never a
silent drop. When C4 lands, each maps to a future `UNVERIFIED` verdict with
that cause recorded; none can ever produce `DIVERGED`:

| Cause | Raised / recorded when | Future `UNVERIFIED` cause |
|---|---|---|
| `EntryPointMissing` (raised) | no explicit argv, and no `[project.scripts]` entry, root `main.py`, or root notebook; or an unreadable `pyproject.toml` | `ENTRYPOINT_MISSING` |
| `EntryPointAmbiguous` (raised) | more than one entry point discovered | `ENTRYPOINT_AMBIGUOUS` |
| C2's `EnvBuildFailed` (raised) | the env build is missing or failed; nothing runs | `ENV_BUILD_FAILED` |
| `WONT_RUN` (recorded) | the argv could not start, or exited non-zero | `WONT_RUN` |
| `TIMEOUT` (recorded) | the process group outlived its timeout and was killed | `TIMEOUT` |
| `STALE_ARTIFACT` (recorded) | an output file's mtime predates the run start | `STALE_ARTIFACT` |
| `NO_ARTIFACT` (recorded) | a successful run wrote no fresh output and nothing to stdout | `NO_ARTIFACT` |
| `ARTIFACT_TOO_LARGE` (recorded) | one output or stream outgrew the per-artifact cap; refused, never truncated | `ARTIFACT_TOO_LARGE` |
| `CAPTURE_LIMIT_EXCEEDED` (recorded) | the run's captured evidence outgrew the total cap | `CAPTURE_LIMIT_EXCEEDED` |

**Offline contract.** Tests never touch the network: every entry point is the
test interpreter running a local program, and the run env sets
``UV_OFFLINE=1``. Notebook capture is built (2026-10-08): a root ``*.ipynb`` is
the fallback entry point, executed through the checkout's own
``jupyter nbconvert --execute --inplace``; each fresh notebook is captured
whole-file (``notebook``) plus one ``notebook_cell`` artifact per output-bearing
cell. **Resource caps** bound the evidence read and stored: one artifact and
the run's total captured bytes, each a recorded cause that governs the
verdicts. A run that floods stdout is still buffered by the runner before the
cap applies (`shortcut: stdout/stderr are capped after the fact, stream them
when a real process floods memory`). Container isolation is still deferred.
"""

from __future__ import annotations

from pathlib import Path

from plumb.intake.checkout import Checkout
from plumb.intake.env import EnvBuild
from plumb.run.capture import (
    Artifact,
    Capture,
    CaptureCaps,
    StaleOutput,
    capture_outputs,
)
from plumb.run.causes import (
    ARTIFACT_TOO_LARGE,
    CAPTURE_LIMIT_EXCEEDED,
    NO_ARTIFACT,
    STALE_ARTIFACT,
    TIMEOUT,
    WONT_RUN,
    EntryPointAmbiguous,
    EntryPointMissing,
)
from plumb.run.entrypoint import EntryPoint, resolve_entrypoint
from plumb.run.runner import RunFailure, RunResult, run_entrypoint
from plumb.run.trace import RunTrace, build_trace, derive_run_id, parse_trace, serialize_trace

__all__ = [
    "ARTIFACT_TOO_LARGE",
    "CAPTURE_LIMIT_EXCEEDED",
    "NO_ARTIFACT",
    "STALE_ARTIFACT",
    "TIMEOUT",
    "WONT_RUN",
    "Artifact",
    "Capture",
    "CaptureCaps",
    "EntryPoint",
    "EntryPointAmbiguous",
    "EntryPointMissing",
    "RunFailure",
    "RunResult",
    "RunTrace",
    "StaleOutput",
    "build_trace",
    "capture_outputs",
    "derive_run_id",
    "parse_trace",
    "resolve_entrypoint",
    "run_and_capture",
    "run_entrypoint",
    "serialize_trace",
]


def run_and_capture(
    checkout: Checkout,
    env_build: EnvBuild | None,
    entrypoint: EntryPoint,
    *,
    run_dir: Path | str | None = None,
    timeout_seconds: float = 1800,
    caps: CaptureCaps | None = None,
) -> tuple[RunTrace, Capture]:
    """Run, capture, and trace; the capture is how C4 reads the outputs."""
    result = run_entrypoint(
        checkout, env_build, entrypoint, run_dir=run_dir, timeout_seconds=timeout_seconds
    )
    capture = capture_outputs(result) if caps is None else capture_outputs(result, caps=caps)
    return build_trace(checkout, result, capture), capture
