"""Notebook spine: a notebook run's artifacts survive trace, record and replay.

Phase S1 of `docs/planning/notebook-capture/spine/plan_20261008.md`. The
notebook aspect added the notebook fallback entry point and `notebook` /
`notebook_cell` artifacts; this file pins that the existing generic mechanisms
— `build_trace`, `write_record`, `plumb verify --from-record` — carry those
artifacts unchanged and need no notebook-specific code. The stub `jupyter` is a
local executable the test writes; there is no kernel and no network.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

from plumb.cli import main
from plumb.cli.record import write_record
from plumb.extract.pipeline import extract_claims
from plumb.intake.checkout import resolve_local
from plumb.intake.env import EnvBuild
from plumb.intake.manifest import scan_manifests
from plumb.run import build_trace, capture_outputs, resolve_entrypoint, run_entrypoint
from plumb.verify import Completed, load_bindings, verify_claims

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent / "verify"))
from verify_helpers import bindings_json  # noqa: E402

OK_BUILD = EnvBuild(ok=True, policy="best-effort", detail="stub")
OLD = 1_000_000_000

PAPER = "# Demo Notebook Paper\n\n## Results\n\nThe AUC was 0.91.\n"
OUTPUTS = [{"output_type": "stream", "name": "stdout", "text": "AUC = 0.91\n"}]
COMMITTED_NOTEBOOK = json.dumps(
    {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["print('AUC = 0.91')"],
            }
        ],
        "nbformat": 4,
        "nbformat_minor": 5,
    }
).encode("utf-8")
_EXECUTED_BODY = json.dumps(
    {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": OUTPUTS,
                "source": ["print('AUC = 0.91')"],
            }
        ],
        "nbformat": 4,
        "nbformat_minor": 5,
    }
)
EXECUTED_NOTEBOOK = _EXECUTED_BODY.encode("utf-8") + b"\n"
CANONICAL_CELL = (
    json.dumps(OUTPUTS, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    + "\n"
).encode("utf-8")
STUB_JUPYTER = f"""#!/bin/sh
cat > analysis.ipynb <<'PLUMB_NOTEBOOK_EOF'
{_EXECUTED_BODY}
PLUMB_NOTEBOOK_EOF
printf 'AUC = 0.91\\n'
"""


def make_checkout(root: Path):
    """A notebook-only checkout, its notebook committed and back-dated like a clone's."""
    root.mkdir(parents=True)
    (root / "analysis.ipynb").write_bytes(COMMITTED_NOTEBOOK)
    (root / "paper.md").write_text(PAPER, encoding="utf-8")
    os.utime(root / "analysis.ipynb", (OLD, OLD))
    os.utime(root / "paper.md", (OLD, OLD))
    return resolve_local(root)


def stub_jupyter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An executable `jupyter` first on PATH that executes the notebook in place."""
    stub = tmp_path / "stub"
    stub.mkdir()
    jupyter = stub / "jupyter"
    jupyter.write_text(STUB_JUPYTER, encoding="utf-8")
    jupyter.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def work_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The CLI's work area for one test: per-test tmp, never the real ~/.plumb-runs."""
    root = tmp_path / "plumb-runs"
    monkeypatch.setattr("plumb.cli.live.WORK_ROOT", root)
    return root


def paper_and_bindings(tmp_path: Path) -> tuple[Path, Path]:
    """The S1 paper and a `<stdout>` binding for its one claim."""
    paper = tmp_path / "paper.md"
    paper.write_text(PAPER, encoding="utf-8")
    claims, _ = extract_claims(PAPER)
    bindings = tmp_path / "bindings.json"
    bindings.write_bytes(
        bindings_json(
            (claims[0], "<stdout>", {"kind": "stdout_regex", "pattern": r"AUC = (\S+)"})
        )
    )
    return paper, bindings


def notebook_argv(paper: Path, repo: Path, bindings: Path) -> list[str]:
    return ["verify", str(paper), str(repo), "--bindings", str(bindings),
            "--no-env-build", "--json"]


def run_dirs(work_root: Path) -> list[Path]:
    return [path for path in work_root.iterdir() if path.name.startswith("run-")]


class TestANotebookRunRecordsAndReplays:
    """Acceptance 2: the record's objects carry the notebook and replay byte-identically."""

    def test_the_record_objects_carry_the_notebook_and_replay_decides(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        checkout = make_checkout(tmp_path / "proj")
        stub_jupyter(tmp_path, monkeypatch)
        entry = resolve_entrypoint(checkout, scan_manifests(checkout))
        assert entry.source == "notebook"
        result = run_entrypoint(
            checkout, OK_BUILD, entry, run_dir=tmp_path / "run", timeout_seconds=60
        )
        assert result.failure is None
        capture = capture_outputs(result)
        trace = build_trace(checkout, result, capture)
        by_relpath = {artifact.relpath: artifact.kind for artifact in trace.artifacts}
        assert by_relpath["analysis.ipynb"] == "notebook"
        assert by_relpath["analysis.ipynb#cell-0"] == "notebook_cell"

        claims, _ = extract_claims(PAPER)
        assert len(claims) == 1
        bindings_bytes = bindings_json(
            (claims[0], "<stdout>", {"kind": "stdout_regex", "pattern": r"AUC = (\S+)"})
        )
        bindings = load_bindings(bindings_bytes, [claim.id for claim in claims])
        verdicts = verify_claims(claims, bindings, Completed(trace, capture))
        assert [verdict.verdict for verdict in verdicts.verdicts] == ["REPRODUCED"]

        record = write_record(
            tmp_path / "record",
            claims=claims,
            bindings_bytes=bindings_bytes,
            trace=trace,
            capture=capture,
            paper_bytes=PAPER.encode("utf-8"),
            paper_format="markdown",
        )
        objects = {path.name: path.read_bytes() for path in (record / "objects").iterdir()}
        assert objects[hashlib.sha256(EXECUTED_NOTEBOOK).hexdigest()] == EXECUTED_NOTEBOOK
        assert objects[hashlib.sha256(CANONICAL_CELL).hexdigest()] == CANONICAL_CELL

        code = main(["verify", "--from-record", str(record), "--json"])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out.encode("utf-8") == (record / "verdicts.json").read_bytes()


class TestANotebookOnlyRepoThroughTheLiveCli:
    """Acceptance S2a: the live CLI runs the stub kernel and captures its notebook."""

    def test_the_claim_is_reproduced_and_the_objects_hold_the_notebook(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, work_root: Path
    ) -> None:
        checkout = make_checkout(tmp_path / "proj")
        stub_jupyter(tmp_path, monkeypatch)
        paper, bindings = paper_and_bindings(tmp_path)

        code = main(notebook_argv(paper, checkout.checkout_dir, bindings))
        captured = capsys.readouterr()
        assert code == 0
        assert captured.err == ""
        document = json.loads(captured.out)
        assert [verdict["verdict"] for verdict in document["verdicts"]] == ["REPRODUCED"]

        runs = run_dirs(work_root)
        assert len(runs) == 1
        objects = {path.name: path.read_bytes() for path in (runs[0] / "objects").iterdir()}
        assert objects[hashlib.sha256(EXECUTED_NOTEBOOK).hexdigest()] == EXECUTED_NOTEBOOK
        assert objects[hashlib.sha256(CANONICAL_CELL).hexdigest()] == CANONICAL_CELL


class TestTheLiveCliIsDeterministicForANotebookRepo:
    """Acceptance S2b: same inputs, one process → byte-identical stdout, one run dir."""

    def test_two_invocations_are_byte_identical(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, work_root: Path
    ) -> None:
        checkout = make_checkout(tmp_path / "proj")
        stub_jupyter(tmp_path, monkeypatch)
        paper, bindings = paper_and_bindings(tmp_path)
        argv = notebook_argv(paper, checkout.checkout_dir, bindings)

        assert main(argv) == 0
        first = capsys.readouterr().out
        assert main(argv) == 0
        second = capsys.readouterr().out
        assert first == second

        runs = run_dirs(work_root)
        assert len(runs) == 1
        assert runs[0].is_dir()
