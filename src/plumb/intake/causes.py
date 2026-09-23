"""Named failure causes for the intake package.

Every failure here is a named cause rather than a silent drop. Downstream,
each maps to a future `UNVERIFIED` verdict with that cause recorded
(`CLAUDE.md` #3); the mapping table lives in the `src/plumb/intake/__init__.py`
module docstring. Intake itself produces records, never verdicts.
"""

from __future__ import annotations

__all__ = [
    "EnvBuildFailed",
    "RevNotFound",
    "SourceNotFound",
    "UnsupportedArchive",
]


class SourceNotFound(RuntimeError):
    """The source path does not exist, is not readable, or is not a git repo."""


class RevNotFound(RuntimeError):
    """The requested revision does not exist in the source repository."""


class UnsupportedArchive(RuntimeError):
    """The archive format is not supported, or the file is not a readable archive."""


class EnvBuildFailed(RuntimeError):
    """The recorded environment-build policy could not be executed."""