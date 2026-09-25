"""Synthetic runs for the verify tests: real local programs through C3, offline.

Mirrors `tests/run/test_capture.py`: a checkout from files on disk, an explicit
entry point running this interpreter, a stub env build. The capture is the real
`capture_outputs` over a real run area, so what C4 reads is exactly what C3
would hand it.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from plumb.intake.checkout import resolve_local
from plumb.intake.env import EnvBuild
from plumb.run.capture import Capture, capture_outputs
from plumb.run.entrypoint import EntryPoint
from plumb.run.runner import RunResult, run_entrypoint

OK_BUILD = EnvBuild(ok=True, policy="best-effort", detail="stub")
OLD = 1_000_000_000  # 2001-09-09, long before any run


def make_checkout(root: Path, files: dict[str, bytes] | None = None, *, backdate: bool = True):
    """A checkout from `files`; committed files are back-dated like a real clone's."""
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in (files or {"README.md": b"# demo\n"}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if backdate:
            os.utime(path, (OLD, OLD))
    return resolve_local(root)


def entry(program: str) -> EntryPoint:
    return EntryPoint(argv=(sys.executable, "-c", program), source="explicit")


def run_program(
    tmp_path: Path, program: str, *, files: dict[str, bytes] | None = None,
    timeout_seconds: float = 60,
) -> tuple[RunResult, Capture]:
    """Run `program` in a fresh checkout of `files`; return the result and its capture."""
    checkout = make_checkout(tmp_path / "proj", files)
    result = run_entrypoint(
        checkout, OK_BUILD, entry(program), run_dir=tmp_path / "run",
        timeout_seconds=timeout_seconds,
    )
    return result, capture_outputs(result)


def writes(relpath: str, data: str | bytes) -> str:
    """A program that writes `data` verbatim to `relpath` in the working copy."""
    payload = data.encode() if isinstance(data, str) else data
    return (
        "import pathlib\n"
        f"p = pathlib.Path({relpath!r})\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        f"p.write_bytes({payload!r})\n"
    )


def prints(data: str | bytes) -> str:
    """A program that writes `data` verbatim to stdout."""
    payload = data.encode() if isinstance(data, str) else data
    return f"import sys\nsys.stdout.buffer.write({payload!r})\n"


def run_full(
    tmp_path: Path, program: str, *, files: dict[str, bytes] | None = None,
    timeout_seconds: float = 60,
):
    """Run `program` and return (checkout, result, capture, trace) — a completed C3 run."""
    from plumb.run.trace import build_trace

    checkout = make_checkout(tmp_path / "proj", files)
    result = run_entrypoint(
        checkout, OK_BUILD, entry(program), run_dir=tmp_path / "run",
        timeout_seconds=timeout_seconds,
    )
    capture = capture_outputs(result)
    return checkout, result, capture, build_trace(checkout, result, capture)


def claim(reported: str, metric: str = "AUC", units: str | None = None):
    """A `Claim` as C1 would admit one, from a paper-shaped value string."""
    from plumb.extract.claim import Claim
    from plumb.extract.location import CharSpan
    from plumb.extract.value import parse_value

    value = parse_value(reported)
    assert value is not None, reported
    return Claim(
        reported_value=value, units=units, metric=metric, location=CharSpan(0, len(reported)),
        artifact_hint=None, tolerance_hint=None,
    )


def bindings_json(*entries: tuple) -> bytes:
    """Bindings from (claim, artifact, locator dict[, extra fields]) tuples."""
    import json

    items = []
    for c, artifact, locator, *extra in entries:
        items.append({"claim_id": c.id, "artifact": artifact, "locator": locator,
                      **(extra[0] if extra else {})})
    return json.dumps({"bindings": items}).encode()
