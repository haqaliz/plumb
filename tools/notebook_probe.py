#!/usr/bin/env python3
"""Recorded dev-time probe of the notebook path (C3 follow-on).

Creates a synthetic notebook-only repo, builds its **real** environment with
`uv sync` (jupyter/nbconvert/ipykernel from the network, dev time only), runs
the repo through the live `plumb verify` CLI, and prints what the run captured:
the executed `.ipynb` whole-file artifact and one canonical `notebook_cell`
artifact per output-bearing cell.

Tests never import this module and never run a real kernel; the offline path is
pinned by `tests/cli/test_notebook_spine.py` with a stub `jupyter`.

Run by hand:
    uv run tools/notebook_probe.py

The output is the evidence that resolve → execute → capture is wired end to end
against a real environment (PRD S1); paste it into the PR description.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from plumb.cli import main
from plumb.cli import live

_PYPROJECT = """\
[project]
name = "plumb-notebook-probe"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["jupyter", "nbconvert", "ipykernel"]

[tool.uv]
package = false
"""

_NOTEBOOK = {
    "cells": [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": ["# Probe"],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": ["print('AUC = 0.91')"],
        },
    ],
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

_PAPER = "# Notebook probe\n\n## Results\n\nA synthetic notebook run, re-derived locally.\n"


def make_repo() -> Path:
    repo = Path(tempfile.mkdtemp(prefix="plumb-notebook-probe-")) / "repo"
    repo.mkdir(parents=True)
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (repo / "analysis.ipynb").write_text(json.dumps(_NOTEBOOK, indent=1), encoding="utf-8")
    return repo


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
    repo = make_repo()
    work = Path(tempfile.mkdtemp(prefix="plumb-notebook-runs-"))
    live.WORK_ROOT = work

    paper = repo.parent / "paper.md"
    paper.write_text(_PAPER, encoding="utf-8")
    bindings = repo.parent / "bindings.json"
    bindings.write_text('{"bindings": []}\n', encoding="utf-8")

    print(f"repo:     {repo}")
    print(f"work:     {work}")
    print("running the live CLI (real uv sync + real kernel, dev time only) ...")
    code = main(["verify", str(paper), str(repo), "--bindings", str(bindings), "--json"])

    runs = sorted(path for path in work.iterdir() if path.name.startswith("run-"))
    print(f"\ncli exit: {code}")
    print(f"run dirs: {[path.name for path in runs]}")
    if len(runs) != 1:
        print("expected exactly one run dir")
        return 1
    objects = sorted((runs[0] / "objects").iterdir())
    kinds: dict[str, int] = {}
    for path in objects:
        blob = path.read_bytes()
        kind = classify(blob)
        kinds[kind] = kinds.get(kind, 0) + 1
        digest = hashlib.sha256(blob).hexdigest()
        print(f"\nobject {digest[:16]}… size={len(blob)} kind={kind}")
        if kind == "notebook_cell":
            print(f"  {blob.decode('utf-8').strip()}")
        elif kind == "notebook":
            document = json.loads(blob.decode("utf-8"))
            print(f"  cells={len(document['cells'])}")
    print(f"\nartifact kinds: {kinds}")
    return 0 if kinds.get("notebook") and kinds.get("notebook_cell") else 1


if __name__ == "__main__":
    sys.exit(main_probe())
