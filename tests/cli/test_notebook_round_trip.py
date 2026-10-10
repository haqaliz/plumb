"""Notebook-cell round-trips: record, replay and bank carry a cell binding verbatim.

Phase 5 of `docs/planning/notebook-cell-locator/locator/plan_20261010.md`,
written failing first (PRD must-have 7): a claim bound to
`analysis.ipynb#cell-0` with a `notebook_cell` locator travels every hop
byte-identically — `write_record` → `read_record` → `verify_claims` →
`cross_check`, `plumb verify --from-record`, and `corpus bank` /
`--from-record --bank`. The bindings file is verbatim bytes at every hop
(record.py:73, replay.py:134, build.py:81, store.py:194); nothing here
re-spells it. The run is a real local program writing a synthetic executed
notebook, as in `tests/verify/test_locate.py::TestNotebookCell`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

from plumb.cli import main
from plumb.cli.record import write_record
from plumb.cli.replay import cross_check, read_record
from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.value import parse_value
from plumb.verify import Completed, load_bindings, serialize_verdicts, verify_claims

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent / "verify"))
from verify_helpers import bindings_json, notebook_bytes, run_full, writes_notebook  # noqa: E402

#: The paper the claim is grounded in; its one value sits at a real span.
PAPER = "# Synthetic paper\n\nAUC was 0.91.\n"
NOTEBOOK = "analysis.ipynb"
CELL = "analysis.ipynb#cell-0"
#: A synthetic executed notebook whose one cell streams the headline number.
CELLS = [
    {
        "cell_type": "code",
        "execution_count": 1,
        "metadata": {},
        "outputs": [{"output_type": "stream", "name": "stdout", "text": ["0.91\n"]}],
        "source": ["print(0.91)"],
    },
]
EXECUTED_NOTEBOOK = notebook_bytes(CELLS)
CANONICAL_CELL = (
    json.dumps(
        CELLS[0]["outputs"], sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    )
    + "\n"
).encode("utf-8")


def notebook_claim() -> Claim:
    """The paper's one claim, grounded at its real span, as C1 would admit it."""
    normalized = normalize_text(PAPER)
    start = normalized.index("0.91")
    value = parse_value("0.91")
    assert value is not None
    return Claim(
        reported_value=value, units=None, metric="AUC",
        location=CharSpan(start, start + len("0.91")),
        artifact_hint=None, tolerance_hint=None,
    )


def notebook_materials(root: Path, *, program: str | None = None):
    """One completed C3/C4 run's materials: (claim, bindings_bytes, trace, capture).

    The claim is bound to `analysis.ipynb#cell-0`'s stream line through the
    `notebook_cell` locator; `program` overrides the default notebook-writing
    program, so a test that puts a local path into stderr must hand it to the
    program another way (an env var), never in `program`.
    """
    claim = notebook_claim()
    if program is None:
        program = writes_notebook(NOTEBOOK, CELLS)
    _checkout, _result, capture, trace = run_full(root, program)
    bindings_bytes = bindings_json(
        (claim, CELL, {"kind": "notebook_cell", "pointer": "/0/text/0"})
    )
    return claim, bindings_bytes, trace, capture


def make_record(tmp_path: Path, claim, bindings_bytes, trace, capture) -> Path:
    """`write_record` on the synthetic paper; the record dir is `tmp_path/record`."""
    return write_record(
        tmp_path / "record", claims=[claim], bindings_bytes=bindings_bytes,
        trace=trace, capture=capture, paper_bytes=PAPER.encode(),
        paper_format="markdown",
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under `root`, as a posix-relative path -> bytes snapshot."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _banked_case_id(out: str) -> str:
    """The case id the `banked <case_id>` line on stdout names."""
    return out.rsplit("banked ", 1)[1].strip()


class TestTheNotebookRecordReplays:
    """A cell-bound claim's record replays byte-identically through the chain."""

    def test_the_record_holds_the_notebook_and_the_cell_and_replays(
        self, tmp_path: Path
    ) -> None:
        claim, bindings_bytes, trace, capture = notebook_materials(tmp_path)
        verdicts = verify_claims(
            [claim], load_bindings(bindings_bytes, [claim.id]), Completed(trace, capture)
        )
        assert verdicts.verdicts[0].verdict == "REPRODUCED"
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        assert (record / "bindings.json").read_bytes() == bindings_bytes
        names = {p.name for p in (record / "objects").iterdir()}
        assert names == {a.sha256 for a in capture.locatable}
        objects = {p.name: p.read_bytes() for p in (record / "objects").iterdir()}
        assert objects[hashlib.sha256(EXECUTED_NOTEBOOK).hexdigest()] == EXECUTED_NOTEBOOK
        assert objects[hashlib.sha256(CANONICAL_CELL).hexdigest()] == CANONICAL_CELL
        claims, bindings, trace2, capture2, paper, paper_format = read_record(record)
        assert paper_format == "markdown"
        assert paper == PAPER.encode()
        rederived = verify_claims(
            claims, load_bindings(bindings, [c.id for c in claims]), Completed(trace2, capture2)
        )
        cross_check(record, rederived)
        assert serialize_verdicts(rederived) == serialize_verdicts(verdicts)

    def test_the_cli_replay_json_is_byte_identical_to_the_record(
        self, tmp_path: Path, capsys
    ) -> None:
        claim, bindings_bytes, trace, capture = notebook_materials(tmp_path)
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        code = main(["verify", "--from-record", str(record), "--json"])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out.encode("utf-8") == (record / "verdicts.json").read_bytes()

    def test_no_local_path_appears_in_any_record_byte(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PLUMB_TEST_LEAK", str(tmp_path))
        claim, bindings_bytes, trace, capture = notebook_materials(
            tmp_path,
            program="import os, sys\nsys.stderr.buffer.write("
            "os.environ['PLUMB_TEST_LEAK'].encode())\n"
            + writes_notebook(NOTEBOOK, CELLS),
        )
        stderr_artifact = next(a for a in capture.artifacts if a.diagnostic_only)
        assert stderr_artifact.kind == "stderr"
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        names = {p.name for p in (record / "objects").iterdir()}
        assert stderr_artifact.sha256 not in names
        leaked = [
            path for path in record.rglob("*")
            if path.is_file() and str(tmp_path).encode() in path.read_bytes()
        ]
        assert leaked == []

    def test_only_the_record_dir_gains_files(self, tmp_path: Path) -> None:
        claim, bindings_bytes, trace, capture = notebook_materials(tmp_path)
        before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
        record_files = {p.relative_to(tmp_path) for p in record.rglob("*") if p.is_file()}
        assert after - before == record_files


class TestTheNotebookRecordBanks:
    """A cell-bound record banks write-once: same case id, second bank a no-op."""

    @pytest.fixture
    def default_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """The default store `corpus/local`, redirected into the test via the cwd."""
        monkeypatch.chdir(tmp_path)
        return tmp_path / "corpus" / "local"

    def test_from_record_bank_folds_the_same_case_as_corpus_bank(
        self, tmp_path: Path, capsys, default_store: Path
    ) -> None:
        claim, bindings_bytes, trace, capture = notebook_materials(tmp_path)
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)

        elsewhere = tmp_path / "elsewhere"
        assert main(["corpus", "bank", str(record), "--store", str(elsewhere)]) == 0
        case_id = _banked_case_id(capsys.readouterr().out)

        code = main(["verify", "--from-record", str(record), "--bank"])
        captured = capsys.readouterr()
        assert code == 0
        assert captured.err == ""
        out = captured.out
        assert "REPRODUCED" in out
        assert out.endswith(f"banked {case_id}\n")
        assert (default_store / case_id / "case.json").is_file()
        assert _tree_bytes(elsewhere / case_id) == _tree_bytes(default_store / case_id)

    def test_a_second_bank_is_a_no_op(
        self, tmp_path: Path, capsys, default_store: Path
    ) -> None:
        claim, bindings_bytes, trace, capture = notebook_materials(tmp_path)
        record = make_record(tmp_path, claim, bindings_bytes, trace, capture)
        assert main(["verify", "--from-record", str(record), "--bank"]) == 0
        case_id = _banked_case_id(capsys.readouterr().out)
        snapshot = _tree_bytes(default_store)

        code = main(["verify", "--from-record", str(record), "--bank"])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.out.endswith(f"already banked: {case_id}\n")
        assert captured.err == ""
        assert _tree_bytes(default_store) == snapshot