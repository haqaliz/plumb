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
| `EntryPointMissing` (raised) | no explicit argv, and no `[project.scripts]` entry or root `main.py`; or an unreadable `pyproject.toml` | `ENTRYPOINT_MISSING` |
| `EntryPointAmbiguous` (raised) | more than one entry point discovered | `ENTRYPOINT_AMBIGUOUS` |
| C2's `EnvBuildFailed` (raised) | the env build is missing or failed; nothing runs | `ENV_BUILD_FAILED` |
| `WONT_RUN` (recorded) | the argv could not start, or exited non-zero | `WONT_RUN` |
| `TIMEOUT` (recorded) | the process group outlived its timeout and was killed | `TIMEOUT` |
| `STALE_ARTIFACT` (recorded) | an output file's mtime predates the run start | `STALE_ARTIFACT` |
| `NO_ARTIFACT` (recorded) | a successful run wrote no fresh output and nothing to stdout | `NO_ARTIFACT` |

**Offline contract.** Tests never touch the network: every entry point is the
test interpreter running a local program, and the run env sets
``UV_OFFLINE=1``. Notebook cell capture is a named follow-on (it needs
nbconvert); resource caps beyond the timeout are recorded, not enforced.
"""

from __future__ import annotations

from pathlib import Path

from plumb.intake.checkout import Checkout
from plumb.intake.env import EnvBuild
from plumb.run.capture import Artifact, Capture, StaleOutput, capture_outputs
from plumb.run.causes import (
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
    "NO_ARTIFACT",
    "STALE_ARTIFACT",
    "TIMEOUT",
    "WONT_RUN",
    "Artifact",
    "Capture",
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
) -> tuple[RunTrace, Capture]:
    """Run, capture, and trace; the capture is how C4 reads the outputs."""
    result = run_entrypoint(
        checkout, env_build, entrypoint, run_dir=run_dir, timeout_seconds=timeout_seconds
    )
    capture = capture_outputs(result)
    return build_trace(checkout, result, capture), capture
