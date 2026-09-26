"""`parse_trace`: a serialized RunTrace read back, exactly (gate-paper G2).

Offline replay (and C6, later) starts from the committed `trace.json`, not from a live run,
so the record must come back as the same `RunTrace` it was written from. Pinned here: the
round trip is the identity for a clean run, a failed run and a run with stale outputs, and
anything that is not a trace this serializer wrote is refused.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

from plumb.intake.checkout import resolve_local
from plumb.intake.env import EnvBuild
from plumb.run import parse_trace, run_and_capture, serialize_trace
from plumb.run.entrypoint import EntryPoint

OK_BUILD = EnvBuild(ok=True, policy="best-effort", detail="stub")
OLD = 1_000_000_000


def trace_of(tmp_path: Path, program: str, files: dict[str, bytes] | None = None):
    root = tmp_path / "proj"
    root.mkdir()
    for rel, data in (files or {"README.md": b"# demo\n"}).items():
        (root / rel).write_bytes(data)
        os.utime(root / rel, (OLD, OLD))
    checkout = resolve_local(root)
    entry = EntryPoint(argv=(sys.executable, "-c", program), source="explicit")
    trace, _ = run_and_capture(checkout, OK_BUILD, entry, run_dir=tmp_path / "run")
    return trace


@pytest.mark.parametrize(
    ("program", "files"),
    [
        ("import json; json.dump({'auc': 0.91}, open('r.json', 'w')); print('AUC = 0.91')", None),
        ("print('about to fail'); raise SystemExit(3)", None),
        ("print('ran')", {"old.json": b'{"auc": 0.8}'}),
    ],
    ids=["clean", "failed", "stale"],
)
def test_the_round_trip_is_the_identity(tmp_path: Path, program: str, files) -> None:
    trace = trace_of(tmp_path, program, files)
    data = serialize_trace(trace)
    assert parse_trace(data) == trace
    assert serialize_trace(parse_trace(data)) == data


@pytest.mark.parametrize(
    "data",
    [b"", b"not json", b"[]", b'{"run_id": "x"}', b'{"run_id": 1}\n', "é".encode("latin-1")],
)
def test_anything_else_is_refused(data: bytes) -> None:
    with pytest.raises(ValueError):
        parse_trace(data)


def test_a_tampered_run_id_is_refused(tmp_path: Path) -> None:
    trace = trace_of(tmp_path, "print('x')")
    data = serialize_trace(trace).replace(trace.run_id.encode(), b"0" * 64)
    with pytest.raises(ValueError, match="run_id"):
        parse_trace(data)
