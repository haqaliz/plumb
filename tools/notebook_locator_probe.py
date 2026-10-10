#!/usr/bin/env python3
"""Recorded dev-time probe: a stub-kernel notebook run to a cell-bound verdict.

One level beyond `tools/notebook_probe.py`: that probe proved resolve →
execute → capture against a real environment with a **vacuous** paper. This
probe runs the live `plumb verify` spine on a synthetic notebook-only repo
whose cell output carries a headline number — an `execute_result`
`{"text/plain": ["0.87"]}` plus the stream line a real run would produce —
binds the paper's two claims to that cell with `notebook_cell` pointers, and
asserts the verdicts decide: one `REPRODUCED` (the paper's 0.87 matches what
the cell wrote) and one `DIVERGED` (the paper's 0.42 does not;
`review_required`).

Nothing here is exercised by pytest, and nothing runs a kernel or touches the
network: `jupyter` on PATH is a stub that fabricates the executed notebook in
place (`tests/cli/test_notebook_spine.py` pattern), the CLI runs with
`--no-env-build`, and the run area is a fresh temp dir. The offline path is
pinned by `tests/cli/test_notebook_spine.py`; this probe is the recorded
dev-time evidence (`docs/planning/notebook-cell-locator/probe_20261010.md`).

Run by hand:
    uv run python tools/notebook_locator_probe.py

The printed output is the evidence; the exit code is 0 iff the expected
verdicts land.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

from plumb.cli import main
from plumb.cli import live
from plumb.extract.pipeline import extract_claims

_PAPER = (
    "# Notebook Locator Probe\n"
    "\n"
    "## Results\n"
    "\n"
    "The AUC was 0.87.\n"
    "\n"
    "The baseline error was 0.42.\n"
)

#: The pointer both claims bind: the executed cell's canonical outputs array,
#: index 1 (`execute_result`), `data.text/plain[0]` (D1 literal ``/`` keys).
_POINTER = "/1/data/text/plain/0"

#: The single output-bearing cell's outputs as the stub's "kernel" writes them.
_OUTPUTS = [
    {
        "name": "stdout",
        "output_type": "stream",
        "text": ["headline AUC = 0.87\n"],
    },
    {
        "data": {"text/plain": ["0.87"]},
        "execution_count": 1,
        "metadata": {},
        "output_type": "execute_result",
    },
]

_NOTEBOOK_METADATA = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}

#: The committed (unexecuted) notebook: one code cell, no outputs.
_COMMITTED_NOTEBOOK = json.dumps(
    {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["print('headline AUC = 0.87')\n", "0.87"],
            }
        ],
        "metadata": _NOTEBOOK_METADATA,
        "nbformat": 4,
        "nbformat_minor": 5,
    },
    indent=1,
).encode("utf-8")

#: The executed notebook the stub writes in place: same cell, its outputs filled.
_EXECUTED_BODY = json.dumps(
    {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": _OUTPUTS,
                "source": ["print('headline AUC = 0.87')\n", "0.87"],
            }
        ],
        "metadata": _NOTEBOOK_METADATA,
        "nbformat": 4,
        "nbformat_minor": 5,
    }
)
_EXECUTED_NOTEBOOK = _EXECUTED_BODY.encode("utf-8") + b"\n"
_EXECUTED_NOTEBOOK_SHA = hashlib.sha256(_EXECUTED_NOTEBOOK).hexdigest()

#: The canonical cell projection capture derives (capture.py `_notebook_cell_outputs`).
CANONICAL_CELL = (
    json.dumps(
        _OUTPUTS,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    + "\n"
).encode("utf-8")
CELL_SHA = hashlib.sha256(CANONICAL_CELL).hexdigest()

#: The expected verdict per claim, keyed by the paper's reported text.
_EXPECTED = {"0.87": "REPRODUCED", "0.42": "DIVERGED"}


class _TextTap:
    """A sys.stdout stand-in: `.buffer` holds the bytes the CLI writes."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def write(self, text: str) -> int:
        return self.buffer.write(text.encode("utf-8"))

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def make_repo() -> tuple[Path, Path, Path]:
    """The synthetic notebook-only repo, plus the paper and bindings beside it."""
    root = Path(tempfile.mkdtemp(prefix="plumb-notebook-locator-"))
    repo = root / "repo"
    repo.mkdir()
    (repo / "analysis.ipynb").write_bytes(_COMMITTED_NOTEBOOK)

    paper = root / "paper.md"
    paper.write_text(_PAPER, encoding="utf-8")
    claims, _ = extract_claims(_PAPER)
    by_reported = {claim.reported_value.text: claim.id for claim in claims}
    assert set(by_reported) == set(_EXPECTED), f"unexpected claims: {sorted(by_reported)}"

    bindings = root / "bindings.json"
    bindings.write_text(
        json.dumps(
            {
                "bindings": [
                    {
                        "claim_id": by_reported[text],
                        "artifact": "analysis.ipynb#cell-0",
                        "locator": {"kind": "notebook_cell", "pointer": _POINTER},
                    }
                    for text in ("0.87", "0.42")
                ]
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return repo, paper, bindings


def stub_jupyter(bin_dir: Path) -> Path:
    """An executable `jupyter` first on PATH that fabricates the executed notebook."""
    stub = bin_dir / "jupyter"
    stub.write_text(
        "#!/bin/sh\n"
        f"cat > analysis.ipynb <<'PLUMB_NOTEBOOK_EOF'\n{_EXECUTED_BODY}\n"
        "PLUMB_NOTEBOOK_EOF\n"
        "printf 'executed analysis.ipynb (stub jupyter, no kernel)\\n'\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
    return stub


def classify(blob: bytes) -> str:
    try:
        document = json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "bytes"
    if isinstance(document, dict) and isinstance(document.get("cells"), list):
        return "notebook"
    if isinstance(document, list) and any(
        isinstance(item, dict) and "output_type" in item for item in document
    ):
        return "notebook_cell"
    return "json"


def main_probe() -> int:
    repo, paper, bindings = make_repo()
    work = Path(tempfile.mkdtemp(prefix="plumb-notebook-locator-runs-"))
    live.WORK_ROOT = work
    stub = stub_jupyter(Path(tempfile.mkdtemp(prefix="plumb-notebook-locator-bin-")))

    print(f"repo:     {repo}")
    print(f"work:     {work}")
    print(f"stub:     {stub}")
    print(
        "running the live CLI (stub jupyter on PATH, --no-env-build, "
        "temp WORK_ROOT, no kernel, no network) ..."
    )
    out = _TextTap()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(
            [
                "verify",
                str(paper),
                str(repo),
                "--bindings",
                str(bindings),
                "--no-env-build",
                "--json",
            ]
        )

    problems: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            problems.append(message)

    print(f"\ncli exit: {code}")
    stderr = err.getvalue()
    print(f"stderr:   {stderr or '(empty)'}")
    check(code == 0, f"cli exit was {code}, expected 0")
    check(stderr == "", f"stderr was not empty: {stderr!r}")

    document = json.loads(out.buffer.getvalue())
    coverage = document["coverage"]
    check(coverage["claims"] == 2, f"coverage claims = {coverage['claims']}, expected 2")
    check(coverage["bound"] == 2, f"coverage bound = {coverage['bound']}, expected 2")
    check(coverage["by_verdict"] == {"DIVERGED": 1, "REPRODUCED": 1, "UNVERIFIED": 0,
                                     "WITHIN-TOLERANCE": 0},
          f"unexpected by_verdict: {coverage['by_verdict']}")

    runs = sorted(path for path in work.iterdir() if path.name.startswith("run-"))
    check(len(runs) == 1, f"expected one run dir, found {len(runs)}")
    run_dir = runs[0] if runs else work
    print(f"run dir:  {run_dir.name}")
    print(f"run id:   {document['run_id']}")

    by_reported = {v["reported_text"]: v for v in document["verdicts"]}
    print("\nper-claim verdicts:")
    for text in sorted(_EXPECTED):
        v = by_reported.get(text)
        check(v is not None, f"no verdict for the claim reporting {text}")
        if v is None:
            continue
        expected = _EXPECTED[text]
        print(
            f"  reported {text!r:>6} -> {v['verdict']:<15} "
            f"located {v['located_text']!r} sha256 {v['sha256'][:16]}\u2026"
        )
        check(v["verdict"] == expected, f"claim {text}: verdict {v['verdict']}, "
              f"expected {expected}")
        check(v["bound"] is True, f"claim {text}: not bound")
        check(v["cause"] is None, f"claim {text}: unexpected cause {v['cause']}")
        check(v["artifact"] == "analysis.ipynb#cell-0",
              f"claim {text}: artifact {v['artifact']}")
        check(v["locator"] == {"kind": "notebook_cell", "pointer": _POINTER},
              f"claim {text}: locator {v['locator']}")
        check(v["located_text"] == "0.87", f"claim {text}: located {v['located_text']!r}")
        check(v["sha256"] == CELL_SHA, f"claim {text}: sha256 {v['sha256']}")
        check(v["rederived"] == "0.87", f"claim {text}: rederived {v['rederived']}")
        if expected == "DIVERGED":
            check(v["review_required"] is True, f"claim {text}: DIVERGED without review_required")

    print("\nthe cli's verdict document, verbatim:")
    print(out.buffer.getvalue().decode("utf-8").rstrip())

    kinds: dict[str, int] = {}
    if runs:
        objects = sorted((runs[0] / "objects").iterdir())
        print("\nrun objects:")
        for path in objects:
            blob = path.read_bytes()
            kind = classify(blob)
            kinds[kind] = kinds.get(kind, 0) + 1
            digest = hashlib.sha256(blob).hexdigest()
            print(f"  object {digest[:16]}\u2026 size={len(blob)} kind={kind}")
            if kind == "notebook_cell":
                print(f"    {blob.decode('utf-8').strip()}")
            elif kind == "notebook":
                print(f"    the executed whole-file notebook")
    print(f"\nartifact kinds: {kinds}")
    check(kinds.get("notebook") == 1, f"expected one notebook object, saw {kinds}")
    check(kinds.get("notebook_cell") == 1, f"expected one notebook_cell object, saw {kinds}")

    if runs:
        objects = {path.name: path.read_bytes() for path in (runs[0] / "objects").iterdir()}
        check(objects.get(CELL_SHA) == CANONICAL_CELL, "cell object bytes are not the projection")
        check(objects.get(_EXECUTED_NOTEBOOK_SHA) == _EXECUTED_NOTEBOOK,
              "whole-notebook object bytes are not the stub's executed notebook")
    print(f"\nexpected hashes: cell {CELL_SHA[:16]}\u2026  notebook {_EXECUTED_NOTEBOOK_SHA[:16]}\u2026")

    if problems:
        print("\nprobe: FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nprobe: the expected verdicts landed — REPRODUCED 1, DIVERGED 1")
    return 0


if __name__ == "__main__":
    sys.exit(main_probe())