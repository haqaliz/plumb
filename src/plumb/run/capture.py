"""Capture: content-addressed outputs and the freshness guard (R3).

`capture_outputs(result)` turns a finished `RunResult` into a `Capture`:

- **Artifacts** — stdout, stderr, and every ``.json``/``.csv`` file in the
  run's working copy that the run wrote. Each is hashed (SHA-256) and its
  bytes are copied into the run's object store at
  ``<run_dir>/objects/<sha256>``. `Capture.read` is the only way back to those
  bytes and it re-checks the hash, so what C4 binds against is exactly what
  was captured, whatever happens to the working copy afterwards.
- **The freshness guard** (`CLAUDE.md` #5). A file whose mtime is strictly
  before the run start is a `StaleOutput`: relpath, mtime and size only. Its
  bytes are never read, so it never reaches the store and cannot be parsed —
  at verdict time it is `UNVERIFIED` with cause `STALE_ARTIFACT`. This
  catches an untouched committed output (the working copy preserves mtimes),
  a file the run back-dates, and a ``cp -p`` of a committed result. A file
  stamped exactly at the run start is fresh. On a filesystem with coarse
  mtimes a file the run wrote can read as stale; that errs towards
  `UNVERIFIED`, never towards a stale value read as fresh.
- **`NO_ARTIFACT`** — a successful run with no fresh file and empty stdout.
  That is a binding problem for C4, not a run failure; a failed run carries
  its own cause instead.

stderr is captured for diagnosis but marked ``diagnostic_only`` and left out
of `Capture.locatable`: no claim is ever bound to it. Symlinks are neither
followed nor captured — a link can point outside the run area. A failed run's
outputs are still captured as evidence; the run's failure governs the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import ClassVar

from plumb.run.causes import NO_ARTIFACT, STALE_ARTIFACT
from plumb.run.runner import RunResult

__all__ = ["Artifact", "Capture", "StaleOutput", "capture_outputs"]

#: File suffixes captured as structured outputs, mapped to the artifact kind.
_OUTPUT_KINDS = {".json": "json", ".csv": "csv"}

STDOUT = "<stdout>"
STDERR = "<stderr>"


@dataclass(frozen=True)
class Artifact:
    """A captured output: what it is, where it came from, and its content address."""

    kind: str  # "csv" | "json" | "stderr" | "stdout"
    relpath: str  # posix path in the working copy, or "<stdout>" / "<stderr>"
    sha256: str
    size: int
    mtime_ns: int | None  # None for streams
    diagnostic_only: bool = False


@dataclass(frozen=True)
class StaleOutput:
    """An output that predates the run: recorded, never read."""

    relpath: str
    mtime_ns: int
    size: int

    cause: ClassVar[str] = STALE_ARTIFACT


@dataclass(frozen=True)
class Capture:
    """Everything one run produced, content-addressed, plus what was refused."""

    store: Path  # absolute; the run's object store, never recorded
    artifacts: tuple[Artifact, ...]  # sorted by (kind, relpath)
    stale: tuple[StaleOutput, ...]  # sorted by relpath
    causes: tuple[str, ...]  # (NO_ARTIFACT,) or ()

    @property
    def locatable(self) -> tuple[Artifact, ...]:
        """The artifacts a claim may be bound to (stderr excluded)."""
        return tuple(a for a in self.artifacts if not a.diagnostic_only)

    def read(self, artifact: Artifact) -> bytes:
        """The captured bytes of `artifact`, verified against its hash."""
        data = (self.store / artifact.sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise ValueError(
                f"object store entry for {artifact.relpath} does not match its hash"
            )
        return data


def capture_outputs(result: RunResult) -> Capture:
    """Hash and store every fresh output of `result`; record the stale ones."""
    store = result.run_dir / "objects"
    store.mkdir(exist_ok=True)

    def stored(data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        (store / digest).write_bytes(data)
        return digest

    artifacts = [
        Artifact("stdout", STDOUT, stored(result.stdout), len(result.stdout), None),
        Artifact(
            "stderr", STDERR, stored(result.stderr), len(result.stderr), None,
            diagnostic_only=True,
        ),
    ]
    stale: list[StaleOutput] = []
    for relpath, path in _output_files(result.workdir):
        info = path.stat()
        if info.st_mtime_ns < result.started_at_ns:
            stale.append(StaleOutput(relpath, info.st_mtime_ns, info.st_size))
            continue
        data = path.read_bytes()
        kind = _OUTPUT_KINDS[path.suffix.lower()]
        artifacts.append(Artifact(kind, relpath, stored(data), len(data), info.st_mtime_ns))

    files = [a for a in artifacts if a.mtime_ns is not None]
    silent = result.failure is None and not files and not result.stdout
    return Capture(
        store=store,
        artifacts=tuple(sorted(artifacts, key=lambda a: (a.kind, a.relpath))),
        stale=tuple(sorted(stale, key=lambda s: s.relpath)),
        causes=(NO_ARTIFACT,) if silent else (),
    )


def _output_files(workdir: Path) -> list[tuple[str, Path]]:
    """Every regular ``.json``/``.csv`` under `workdir`, as (posix relpath, path)."""
    found = []
    for dirpath, _dirnames, filenames in os.walk(workdir, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() in _OUTPUT_KINDS and not path.is_symlink():
                found.append((path.relative_to(workdir).as_posix(), path))
    return sorted(found)
