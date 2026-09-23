"""Named failure causes for the run package.

Two shapes, one rule — every failure is named, never a silent drop:

- **Raised** causes stop the run before anything executes: there is nothing
  to trace, so the caller gets an exception, exactly as intake does.
  `EntryPointMissing` and `EntryPointAmbiguous` are these. (A failed env build
  arrives as C2's `EnvBuildFailed` and is re-raised unchanged.)
- **Recorded** causes describe a run that did happen: the process started,
  so its argv, exit code and output are evidence worth keeping. `WONT_RUN`,
  `TIMEOUT`, `STALE_ARTIFACT` and `NO_ARTIFACT` are recorded on the result,
  capture, and trace rather than raised.

Each name is the future `UNVERIFIED` cause (`CLAUDE.md` #3); the mapping table
lives in the `src/plumb/run/__init__.py` module docstring. Nothing here emits
a verdict.
"""

from __future__ import annotations

__all__ = [
    "NO_ARTIFACT",
    "STALE_ARTIFACT",
    "TIMEOUT",
    "WONT_RUN",
    "EntryPointAmbiguous",
    "EntryPointMissing",
]

#: The process could not start, or exited non-zero.
WONT_RUN = "WONT_RUN"
#: The process outlived its timeout and was killed.
TIMEOUT = "TIMEOUT"
#: An output file whose mtime predates the run start: recorded, never parsed.
STALE_ARTIFACT = "STALE_ARTIFACT"
#: The run succeeded but produced nothing capturable (no fresh file, empty stdout).
NO_ARTIFACT = "NO_ARTIFACT"


class EntryPointMissing(RuntimeError):
    """No entry point was given and none could be discovered."""

    cause = "ENTRYPOINT_MISSING"


class EntryPointAmbiguous(RuntimeError):
    """More than one entry point was discovered; Plumb does not guess."""

    cause = "ENTRYPOINT_AMBIGUOUS"
