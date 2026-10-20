"""Capture: content-addressed outputs and the freshness guard (R3).

`capture_outputs(result)` turns a finished `RunResult` into a `Capture`:

- **Artifacts** — stdout, stderr, and every ``.json``/``.csv``/``.ipynb``
  file in the run's working copy that the run wrote. Each is hashed (SHA-256)
  and its bytes are copied into the run's object store at
  ``<run_dir>/objects/<sha256>``. `Capture.read` is the only way back to those
  bytes and it re-checks the hash, so what C4 binds against is exactly what
  was captured, whatever happens to the working copy afterwards.
  A fresh notebook is additionally decomposed: every cell whose ``outputs`` is
  a non-empty list becomes one `notebook_cell` artifact at
  ``<notebook-relpath>#cell-<i>`` (the cell's 0-based index in the notebook's
  ``cells`` array), holding the canonical JSON projection of that cell's
  outputs. Decomposition is all-or-nothing: a notebook whose JSON, ``cells``,
  or any cell's projection cannot be canonicalized keeps its whole-file
  artifact, gains zero cell artifacts, and raises no new cause.
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
import json
import os
from pathlib import Path
from typing import ClassVar

from plumb.run.causes import (
    ARTIFACT_TOO_LARGE,
    CAPTURE_LIMIT_EXCEEDED,
    NO_ARTIFACT,
    STALE_ARTIFACT,
)
from plumb.run.runner import RunResult

__all__ = ["Artifact", "Capture", "CaptureCaps", "StaleOutput", "capture_outputs"]

#: File suffixes captured as structured outputs, mapped to the artifact kind.
_OUTPUT_KINDS = {".json": "json", ".csv": "csv"}

#: A notebook's suffix; captured whole-file and decomposed into cell artifacts.
_NOTEBOOK_SUFFIX = ".ipynb"

STDOUT = "<stdout>"
STDERR = "<stderr>"


@dataclass(frozen=True)
class CaptureCaps:
    """Evidence caps, in bytes; `None` means unbounded."""

    max_artifact_bytes: int | None = 64 * 1024 * 1024
    max_total_bytes: int | None = 256 * 1024 * 1024


DEFAULT_CAPS = CaptureCaps()


@dataclass(frozen=True)
class Artifact:
    """A captured output: what it is, where it came from, and its content address."""

    kind: str  # "csv" | "json" | "notebook" | "notebook_cell" | "stderr" | "stdout"
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


def capture_outputs(result: RunResult, *, caps: CaptureCaps = DEFAULT_CAPS) -> Capture:
    """Hash and store every fresh output of `result`; record the stale and capped ones.

    A file over a cap is refused before it is read (its size is known from `stat`), so the cap
    bounds the bytes read, not just the bytes stored. The cap is never a truncation: an over-cap
    artifact is absent and the run carries the cause, which governs every verdict.
    """
    store = result.run_dir / "objects"
    store.mkdir(exist_ok=True)
    causes: list[str] = []
    total = 0

    def over(size: int) -> bool:
        """True when this artifact breaks a cap; records the cause and counts nothing."""
        nonlocal total
        if caps.max_artifact_bytes is not None and size > caps.max_artifact_bytes:
            causes.append(ARTIFACT_TOO_LARGE)
            return True
        if caps.max_total_bytes is not None and total + size > caps.max_total_bytes:
            causes.append(CAPTURE_LIMIT_EXCEEDED)
            return True
        total += size
        return False

    def stored(data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        (store / digest).write_bytes(data)
        return digest

    artifacts: list[Artifact] = []
    for kind, relpath, data, diagnostic in (
        ("stdout", STDOUT, result.stdout, False),
        ("stderr", STDERR, result.stderr, True),
    ):
        if over(len(data)):
            continue
        artifacts.append(
            Artifact(kind, relpath, stored(data), len(data), None, diagnostic)
        )
    stale: list[StaleOutput] = []
    for relpath, path in _output_files(result.workdir):
        info = path.stat()
        if info.st_mtime_ns < result.started_at_ns:
            stale.append(StaleOutput(relpath, info.st_mtime_ns, info.st_size))
            continue
        if over(info.st_size):
            continue
        data = path.read_bytes()
        suffix = path.suffix.lower()
        kind = "notebook" if suffix == _NOTEBOOK_SUFFIX else _OUTPUT_KINDS[suffix]
        artifacts.append(Artifact(kind, relpath, stored(data), len(data), info.st_mtime_ns))
        if kind == "notebook":
            for index, canonical in _notebook_cell_outputs(data):
                if over(len(canonical)):
                    continue
                artifacts.append(
                    Artifact(
                        "notebook_cell",
                        f"{relpath}#cell-{index}",
                        stored(canonical),
                        len(canonical),
                        info.st_mtime_ns,
                    )
                )

    files = [a for a in artifacts if a.mtime_ns is not None]
    silent = result.failure is None and not files and not result.stdout and not causes
    return Capture(
        store=store,
        artifacts=tuple(sorted(artifacts, key=lambda a: (a.kind, a.relpath))),
        stale=tuple(sorted(stale, key=lambda s: s.relpath)),
        causes=tuple(sorted(set(causes))) if causes else ((NO_ARTIFACT,) if silent else ()),
    )


def _notebook_cell_outputs(data: bytes) -> list[tuple[int, bytes]]:
    """The canonical projection of each output-bearing cell, or [] if undecomposable.

    All-or-nothing: every projection is built in memory before any is stored,
    so one bad cell leaves the notebook whole-file only.
    """
    try:
        document = json.loads(data.decode("utf-8"))
        if not isinstance(document, dict) or not isinstance(document.get("cells"), list):
            return []
        projected = []
        for index, cell in enumerate(document["cells"]):
            if not isinstance(cell, dict):
                continue
            outputs = cell.get("outputs")
            if not isinstance(outputs, list) or not outputs:
                continue
            canonical = (
                json.dumps(
                    outputs,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
            projected.append((index, canonical))
    except (ValueError, TypeError, UnicodeDecodeError):
        return []
    return projected


def _output_files(workdir: Path) -> list[tuple[str, Path]]:
    """Every regular ``.json``/``.csv``/``.ipynb`` under `workdir`, as (posix relpath, path)."""
    found = []
    for dirpath, _dirnames, filenames in os.walk(workdir, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            suffix = path.suffix.lower()
            captured = suffix in _OUTPUT_KINDS or suffix == _NOTEBOOK_SUFFIX
            if captured and not path.is_symlink():
                found.append((path.relative_to(workdir).as_posix(), path))
    return sorted(found)
