"""Locating a bound value in what the run actually produced (M2).

`locate(binding, capture)` returns the verbatim located text, its strict
`Decimal`, its written precision, and the artifact's hash — or a named cause.
Bytes are read only through `Capture.read` (hash re-checked), and a stale
output's bytes are never read at all (`CLAUDE.md` #5).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from plumb.run.capture import Artifact, Capture
from plumb.verify import causes
from plumb.verify.bindings import load_bindings
from plumb.verify.locate import Located, Unlocated, locate
from verify_helpers import notebook_bytes, prints, run_program, writes, writes_notebook


def bind(artifact: str, locator: dict):
    raw = json.dumps(
        {"bindings": [{"claim_id": "c", "artifact": artifact, "locator": locator}]}
    ).encode()
    return load_bindings(raw, ["c"])["c"]


def pointer(p: str, artifact: str = "results.json"):
    return bind(artifact, {"kind": "json_pointer", "pointer": p})


def regex(pattern: str):
    return bind("<stdout>", {"kind": "stdout_regex", "pattern": pattern})


def cell(column: str, key: str, value: str, artifact: str = "table.csv"):
    return bind(artifact, {"kind": "csv_cell", "column": column, "row": {key: value}})


def notebook_cell(p: str, artifact: str = "analysis.ipynb#cell-0"):
    return bind(artifact, {"kind": "notebook_cell", "pointer": p})


def notebook_table(p: str, table: dict, artifact: str = "analysis.ipynb#cell-0"):
    return bind(artifact, {"kind": "notebook_cell", "pointer": p, "table": table})


def json_run(tmp_path: Path, text: str) -> Capture:
    return run_program(tmp_path, writes("results.json", text))[1]


def stale_cell_capture(tmp_path: Path, cells: list[dict]) -> Capture:
    """A stale notebook with cell artifacts leaked in, as if capture had not refused them."""
    _, capture = run_program(
        tmp_path, prints("done\n"), files={"analysis.ipynb": notebook_bytes(cells)}
    )
    (stale,) = capture.stale
    assert stale.relpath == "analysis.ipynb"
    canonical = (
        json.dumps(
            cells[0]["outputs"], sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    (capture.store / digest).write_bytes(canonical)
    leaked = Artifact(
        "notebook_cell", "analysis.ipynb#cell-0", digest, len(canonical), stale.mtime_ns
    )
    return replace(
        capture,
        artifacts=tuple(sorted((*capture.artifacts, leaked), key=lambda a: (a.kind, a.relpath))),
    )


def cause_of(outcome) -> str:
    assert isinstance(outcome, Unlocated), outcome
    return outcome.cause


class TestJsonPointer:
    def test_locates_a_number_with_its_hash(self, tmp_path: Path) -> None:
        capture = json_run(tmp_path, '{"metrics": {"auc": 0.8712}}')
        located = locate(pointer("/metrics/auc"), capture)
        assert isinstance(located, Located)
        assert located.text == "0.8712"
        assert type(located.value) is Decimal and located.value == Decimal("0.8712")
        assert located.half_unit == Decimal("0.00005")
        assert located.relpath == "results.json"
        artifact = next(a for a in capture.artifacts if a.relpath == "results.json")
        assert located.sha256 == artifact.sha256

    @pytest.mark.parametrize(
        ("literal", "half"),
        [("0.870", "0.0005"), ("12", "0.5"), ("1.5e3", "50"), ("-0", "0.5"), ("0.1", "0.05")],
    )
    def test_keeps_the_literal_as_written(self, tmp_path: Path, literal: str, half: str) -> None:
        located = locate(pointer("/v"), json_run(tmp_path, '{"v": %s}' % literal))
        assert located.text == literal
        assert located.value == Decimal(literal)
        assert located.half_unit == Decimal(half)

    def test_a_decimal_string_leaf_is_read_strictly(self, tmp_path: Path) -> None:
        located = locate(pointer("/v"), json_run(tmp_path, '{"v": " 0.87 "}'))
        assert located.value == Decimal("0.87")

    def test_walks_arrays_and_escapes(self, tmp_path: Path) -> None:
        capture = json_run(tmp_path, '{"a/b": {"~c": [1, 2.5]}}')
        assert locate(pointer("/a~1b/~0c/1"), capture).value == Decimal("2.5")

    def test_the_empty_pointer_is_the_whole_document(self, tmp_path: Path) -> None:
        assert locate(pointer(""), json_run(tmp_path, "0.5")).value == Decimal("0.5")

    @pytest.mark.parametrize("p", ["/metrics/f1", "/metrics/auc/x", "/list/2", "/list/01",
                                   "/list/-", "/list/x"])
    def test_a_miss_is_no_binding(self, tmp_path: Path, p: str) -> None:
        capture = json_run(tmp_path, '{"metrics": {"auc": 0.87}, "list": [1, 2]}')
        assert cause_of(locate(pointer(p), capture)) == causes.NO_BINDING

    def test_a_duplicate_key_is_ambiguous(self, tmp_path: Path) -> None:
        capture = json_run(tmp_path, '{"auc": 0.87, "auc": 0.95}')
        assert cause_of(locate(pointer("/auc"), capture)) == causes.AMBIGUOUS_BINDING

    @pytest.mark.parametrize(
        "leaf", ["true", "null", '"n/a"', '"87%"', "[0.87]", '{"x": 1}', '"1,000"']
    )
    def test_a_non_number_leaf_is_unparseable(self, tmp_path: Path, leaf: str) -> None:
        capture = json_run(tmp_path, '{"v": %s}' % leaf)
        assert cause_of(locate(pointer("/v"), capture)) == causes.UNPARSEABLE_VALUE

    @pytest.mark.parametrize("text", ['{"v": NaN}', '{"v": Infinity}', "{not json", "\xff"])
    def test_an_unreadable_document_is_unparseable(self, tmp_path: Path, text: str) -> None:
        capture = run_program(tmp_path, writes("results.json", text.encode("latin-1")))[1]
        assert cause_of(locate(pointer("/v"), capture)) == causes.UNPARSEABLE_VALUE


class TestStdoutRegex:
    def test_locates_the_one_group(self, tmp_path: Path) -> None:
        capture = run_program(tmp_path, prints("AUC = 0.8712\nn = 300\n"))[1]
        located = locate(regex(r"AUC = (\S+)"), capture)
        assert (located.text, located.value, located.relpath) == (
            "0.8712", Decimal("0.8712"), "<stdout>",
        )

    def test_no_match_is_no_binding(self, tmp_path: Path) -> None:
        capture = run_program(tmp_path, prints("F1 = 0.8\n"))[1]
        assert cause_of(locate(regex(r"AUC = (\S+)"), capture)) == causes.NO_BINDING

    def test_two_matches_are_ambiguous(self, tmp_path: Path) -> None:
        capture = run_program(tmp_path, prints("AUC = 0.87\nAUC = 0.91\n"))[1]
        assert cause_of(locate(regex(r"AUC = (\S+)"), capture)) == causes.AMBIGUOUS_BINDING

    def test_a_non_number_group_is_unparseable(self, tmp_path: Path) -> None:
        capture = run_program(tmp_path, prints("AUC = 87%\n"))[1]
        assert cause_of(locate(regex(r"AUC = (\S+)"), capture)) == causes.UNPARSEABLE_VALUE

    def test_undecodable_stdout_is_unparseable(self, tmp_path: Path) -> None:
        capture = run_program(tmp_path, prints(b"AUC = \xff\n"))[1]
        assert cause_of(locate(regex(r"AUC = (\S+)"), capture)) == causes.UNPARSEABLE_VALUE

    def test_a_group_that_did_not_participate_is_no_binding(self, tmp_path: Path) -> None:
        capture = run_program(tmp_path, prints("AUC\n"))[1]
        assert cause_of(locate(regex(r"AUC(?: = (\S+))?"), capture)) == causes.NO_BINDING


class TestCsvCell:
    TABLE = "model,auc,n\nA,0.8712,300\nB,0.91,250\n"

    def csv_run(self, tmp_path: Path, text: str | bytes) -> Capture:
        return run_program(tmp_path, writes("table.csv", text))[1]

    def test_locates_the_keyed_cell(self, tmp_path: Path) -> None:
        located = locate(cell("auc", "model", "A"), self.csv_run(tmp_path, self.TABLE))
        assert (located.text, located.value, located.relpath) == (
            "0.8712", Decimal("0.8712"), "table.csv",
        )

    def test_a_byte_order_mark_is_not_part_of_the_header(self, tmp_path: Path) -> None:
        capture = self.csv_run(tmp_path, b"\xef\xbb\xbf" + self.TABLE.encode())
        assert locate(cell("auc", "model", "B"), capture).value == Decimal("0.91")

    @pytest.mark.parametrize(
        ("column", "key", "value"),
        [("f1", "model", "A"), ("auc", "arm", "A"), ("auc", "model", "C")],
    )
    def test_a_miss_is_no_binding(self, tmp_path: Path, column: str, key: str, value: str) -> None:
        capture = self.csv_run(tmp_path, self.TABLE)
        assert cause_of(locate(cell(column, key, value), capture)) == causes.NO_BINDING

    def test_two_matching_rows_are_ambiguous(self, tmp_path: Path) -> None:
        capture = self.csv_run(tmp_path, "model,auc\nA,0.87\nA,0.9\n")
        assert cause_of(locate(cell("auc", "model", "A"), capture)) == causes.AMBIGUOUS_BINDING

    def test_a_duplicated_header_column_is_ambiguous(self, tmp_path: Path) -> None:
        capture = self.csv_run(tmp_path, "model,auc,auc\nA,0.87,0.9\n")
        assert cause_of(locate(cell("auc", "model", "A"), capture)) == causes.AMBIGUOUS_BINDING

    def test_an_empty_file_is_no_binding(self, tmp_path: Path) -> None:
        capture = self.csv_run(tmp_path, "")
        assert cause_of(locate(cell("auc", "model", "A"), capture)) == causes.NO_BINDING

    def test_a_short_row_is_no_binding(self, tmp_path: Path) -> None:
        capture = self.csv_run(tmp_path, "model,n,auc\nA,300\n")
        assert cause_of(locate(cell("auc", "model", "A"), capture)) == causes.NO_BINDING

    def test_a_non_number_cell_is_unparseable(self, tmp_path: Path) -> None:
        capture = self.csv_run(tmp_path, "model,auc\nA,n/a\n")
        assert cause_of(locate(cell("auc", "model", "A"), capture)) == causes.UNPARSEABLE_VALUE

    def test_undecodable_bytes_are_unparseable(self, tmp_path: Path) -> None:
        capture = self.csv_run(tmp_path, b"model,auc\nA,\xff\n")
        assert cause_of(locate(cell("auc", "model", "A"), capture)) == causes.UNPARSEABLE_VALUE


class TestNotebookCell:
    """A value in a cell's canonical outputs array (C3 notebook capture → C4 locate)."""

    CELLS = [
        {
            "cell_type": "code",
            "execution_count": 1,
            "metadata": {},
            "outputs": [
                {"output_type": "stream", "name": "stdout", "text": ["0.87\n"], "value": 0.87},
            ],
            "source": ["print(0.87)"],
        },
        {
            "cell_type": "code",
            "execution_count": 2,
            "metadata": {},
            "outputs": [
                {"output_type": "execute_result", "execution_count": 2,
                 "data": {"text/plain": ["0.870"]}, "metadata": {}},
            ],
            "source": ["0.870"],
        },
    ]

    def notebook_run(self, tmp_path: Path) -> Capture:
        return run_program(tmp_path, writes_notebook("analysis.ipynb", self.CELLS))[1]

    def test_a_stream_line_is_located_verbatim(self, tmp_path: Path) -> None:
        capture = self.notebook_run(tmp_path)
        located = locate(notebook_cell("/0/text/0"), capture)
        assert isinstance(located, Located)
        assert located.text == "0.87\n"
        assert type(located.value) is Decimal and located.value == Decimal("0.87")
        assert located.half_unit == Decimal("0.005")
        assert located.relpath == "analysis.ipynb#cell-0"
        artifact = next(
            a for a in capture.artifacts if a.relpath == "analysis.ipynb#cell-0"
        )
        assert located.sha256 == artifact.sha256

    def test_an_execute_result_leaf_is_located(self, tmp_path: Path) -> None:
        located = locate(
            notebook_cell("/0/data/text/plain/0", "analysis.ipynb#cell-1"),
            self.notebook_run(tmp_path),
        )
        assert located.text == "0.870"
        assert type(located.value) is Decimal and located.value == Decimal("0.870")
        assert located.half_unit == Decimal("0.0005")

    def test_an_escaped_slash_key_still_resolves(self, tmp_path: Path) -> None:
        located = locate(
            notebook_cell("/0/data/text~1plain/0", "analysis.ipynb#cell-1"),
            self.notebook_run(tmp_path),
        )
        assert located.text == "0.870"

    def test_a_number_leaf_is_transported_as_its_json_text(self, tmp_path: Path) -> None:
        located = locate(notebook_cell("/0/value"), self.notebook_run(tmp_path))
        assert isinstance(located, Located)
        assert located.text == "0.87"
        assert type(located.value) is Decimal and located.value == Decimal("0.87")
        assert located.half_unit == Decimal("0.005")

    def test_an_unresolved_pointer_is_no_binding(self, tmp_path: Path) -> None:
        capture = self.notebook_run(tmp_path)
        assert cause_of(locate(notebook_cell("/9/text/0"), capture)) == causes.NO_BINDING

    def test_a_list_leaf_is_unparseable(self, tmp_path: Path) -> None:
        capture = self.notebook_run(tmp_path)
        assert cause_of(locate(notebook_cell("/0/text"), capture)) == causes.UNPARSEABLE_VALUE

    def test_a_missing_cell_artifact_is_no_binding(self, tmp_path: Path) -> None:
        capture = self.notebook_run(tmp_path)
        assert cause_of(
            locate(notebook_cell("/0/text/0", "analysis.ipynb#cell-9"), capture)
        ) == causes.NO_BINDING

    def test_a_json_artifact_is_refused_before_anything_is_read(self, tmp_path: Path) -> None:
        capture = json_run(tmp_path, '{"auc": 0.87}')
        binding = notebook_cell("/0/text/0", "results.json")
        assert binding.invalid
        assert cause_of(locate(binding, capture)) == causes.BINDING_INVALID


TABLE_HTML = (
    '<style type="text/css">\n</style>\n<table id="T_1" class="dataframe">\n'
    "  <thead>\n"
    '    <tr style="text-align: right;">\n'
    '      <th class="blank level0" >&nbsp;</th>\n'
    '      <th class="col_heading level0 col0" >Scenario</th>\n'
    '      <th class="col_heading level0 col1" >a</th>\n'
    '      <th class="col_heading level0 col2" >T_AGI (yr)</th>\n'
    '      <th class="col_heading level0 col3" >T_ASI (yr)</th>\n'
    '      <th class="col_heading level0 col4" >ΔT_AGI→ASI (yr)</th>\n'
    "    </tr>\n"
    "  </thead>\n"
    "  <tbody>\n"
    "    <tr>\n"
    '      <th class="row_heading level0 row0" >0</th>\n'
    '      <td class="data row0 col0" >No-RSI baseline</td>\n'
    '      <td class="data row0 col1" >0.0</td>\n'
    '      <td class="data row0 col2" >24.00</td>\n'
    '      <td class="data row0 col3" >96.00</td>\n'
    '      <td class="data row0 col4" >72.00</td>\n'
    "    </tr>\n"
    "    <tr>\n"
    '      <th class="row_heading level0 row1" >1</th>\n'
    '      <td class="data row1 col0" >Smooth scaling</td>\n'
    '      <td class="data row1 col1" >0.5</td>\n'
    '      <td class="data row1 col2" >21.35</td>\n'
    '      <td class="data row1 col3" >74.13</td>\n'
    '      <td class="data row1 col4" >52.79</td>\n'
    "    </tr>\n"
    "    <tr>\n"
    '      <th class="row_heading level0 row2" >2</th>\n'
    '      <td class="data row2 col0" >Weak supercriticality</td>\n'
    '      <td class="data row2 col1" >3.0</td>\n'
    '      <td class="data row2 col2" >12.90</td>\n'
    '      <td class="data row2 col3" >24.73</td>\n'
    '      <td class="data row2 col4" >11.83</td>\n'
    "    </tr>\n"
    "  </tbody>\n"
    "</table>\n"
)

#: nbformat stores a multiline mime payload as one string per line (keepends).
TABLE_HTML_LINES = list(TABLE_HTML.splitlines(True))

TABLE_CELLS = [
    {
        "cell_type": "code",
        "execution_count": 1,
        "metadata": {},
        "outputs": [
            {
                "output_type": "display_data",
                "data": {
                    "text/html": TABLE_HTML_LINES,
                    "text/plain": ["<pandas.core.style.Styler object at 0x2a1>"],
                },
                "metadata": {},
            }
        ],
        "source": ["df.style"],
    },
]


class TestNotebookTable:
    """N1: `table` pins one `<td>` of the pointed HTML leaf's grid."""

    @pytest.mark.parametrize(
        ("row", "column", "text"),
        [(0, 2, "24.00"), (0, 3, "96.00"), (0, 4, "72.00"), (2, 2, "12.90")],
    )
    def test_addresses_the_grid_cell_verbatim(
        self, tmp_path: Path, row: int, column: int, text: str
    ) -> None:
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", TABLE_CELLS))[1]
        located = locate(
            notebook_table("/0/data/text/html", {"row": row, "column": column}), capture
        )
        assert isinstance(located, Located)
        assert located.text == text
        assert type(located.value) is Decimal and located.value == Decimal(text)
        assert located.half_unit == Decimal("0.005")

    def test_a_cell_carries_the_artifact_relpath_and_hash(self, tmp_path: Path) -> None:
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", TABLE_CELLS))[1]
        located = locate(
            notebook_table("/0/data/text/html", {"row": 2, "column": 2}), capture
        )
        assert isinstance(located, Located)
        assert located.relpath == "analysis.ipynb#cell-0"
        artifact = next(
            a for a in capture.artifacts if a.relpath == "analysis.ipynb#cell-0"
        )
        assert located.sha256 == artifact.sha256

    def test_the_header_row_does_not_consume_a_row_index(self, tmp_path: Path) -> None:
        # The `<thead>` `<th>`-only row is not a grid row (the converted table
        # grid's data rows are 0-based), so row 0 is the first data row.
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", TABLE_CELLS))[1]
        located = locate(
            notebook_table("/0/data/text/html", {"row": 0, "column": 2}), capture
        )
        assert isinstance(located, Located)
        assert located.text == "24.00"

    def test_a_single_string_html_leaf_is_addressed(self, tmp_path: Path) -> None:
        cells = [{
            "cell_type": "code", "execution_count": 1, "metadata": {},
            "outputs": [{"output_type": "display_data",
                         "data": {"text/html": "<table><tr><td>0.87</td></tr></table>"},
                         "metadata": {}}],
            "source": ["s"],
        }]
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", cells))[1]
        located = locate(
            notebook_table("/0/data/text/html", {"row": 0, "column": 0}), capture
        )
        assert isinstance(located, Located)
        assert located.text == "0.87"
        assert located.half_unit == Decimal("0.005")

    def test_a_cell_containing_markup_yields_the_stripped_text(self, tmp_path: Path) -> None:
        cells = [{
            "cell_type": "code", "execution_count": 1, "metadata": {},
            "outputs": [{"output_type": "display_data",
                         "data": {"text/html": "<table><tr><td><b>12.90</b></td></tr></table>"},
                         "metadata": {}}],
            "source": ["s"],
        }]
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", cells))[1]
        located = locate(
            notebook_table("/0/data/text/html", {"row": 0, "column": 0}), capture
        )
        assert isinstance(located, Located)
        assert located.text == "12.90"

    def test_an_entity_in_a_cell_is_not_decoded(self, tmp_path: Path) -> None:
        cells = [{
            "cell_type": "code", "execution_count": 1, "metadata": {},
            "outputs": [{"output_type": "display_data",
                         "data": {"text/html": "<table><tr><td>&nbsp;</td></tr></table>"},
                         "metadata": {}}],
            "source": ["s"],
        }]
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", cells))[1]
        located = locate(
            notebook_table("/0/data/text/html", {"row": 0, "column": 0}), capture
        )
        assert isinstance(located, Unlocated)
        assert located.cause == causes.UNPARSEABLE_VALUE

    @pytest.mark.parametrize(("row", "column"), [(3, 0), (9, 9), (0, 5)])
    def test_an_out_of_range_cell_is_no_binding(
        self, tmp_path: Path, row: int, column: int
    ) -> None:
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", TABLE_CELLS))[1]
        assert cause_of(
            locate(notebook_table("/0/data/text/html", {"row": row, "column": column}),
                   capture)
        ) == causes.NO_BINDING

    def test_a_leaf_without_a_td_is_no_binding(self, tmp_path: Path) -> None:
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", TABLE_CELLS))[1]
        assert cause_of(
            locate(notebook_table("/0/data/text/plain/0", {"row": 0, "column": 0}),
                   capture)
        ) == causes.NO_BINDING

    def test_a_table_shape_without_a_single_td_is_no_binding(self, tmp_path: Path) -> None:
        cells = [{
            "cell_type": "code", "execution_count": 1, "metadata": {},
            "outputs": [{"output_type": "display_data",
                         "data": {"text/html": "<table><tr><th>x</th></tr></table>"},
                         "metadata": {}}],
            "source": ["s"],
        }]
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", cells))[1]
        assert cause_of(
            locate(notebook_table("/0/data/text/html", {"row": 0, "column": 0}), capture)
        ) == causes.NO_BINDING

    def test_a_pointed_plain_text_leaf_without_a_td_is_no_binding(
        self, tmp_path: Path
    ) -> None:
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", TABLE_CELLS))[1]
        assert cause_of(
            locate(notebook_table("/0/data/text/plain", {"row": 0, "column": 0}), capture)
        ) == causes.NO_BINDING

    def test_a_pointed_node_that_cannot_be_html_is_unparseable(self, tmp_path: Path) -> None:
        cells = [{
            "cell_type": "code", "execution_count": 1, "metadata": {},
            "outputs": [{"output_type": "display_data",
                         "data": {"text/html": ["<table><tr><td>0.87</td></tr></table>", 7]},
                         "metadata": {}}],
            "source": ["s"],
        }]
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", cells))[1]
        assert cause_of(
            locate(notebook_table("/0/data/text/html", {"row": 0, "column": 0}), capture)
        ) == causes.UNPARSEABLE_VALUE

    def test_float_repr_gives_a_zero_half_unit(self, tmp_path: Path) -> None:
        raw_bindings = json.dumps({
            "bindings": [{
                "claim_id": "c", "artifact": "analysis.ipynb#cell-0",
                "locator": {"kind": "notebook_cell", "pointer": "/0/data/text/html",
                            "table": {"row": 2, "column": 2}},
                "float_repr": True,
            }],
        }).encode()
        binding = load_bindings(raw_bindings, ["c"])["c"]
        capture = run_program(tmp_path, writes_notebook("analysis.ipynb", TABLE_CELLS))[1]
        located = locate(binding, capture)
        assert isinstance(located, Located)
        assert located.text == "12.90"
        assert located.value == Decimal("12.90")
        assert located.half_unit == 0


class TestTargets:
    def test_an_invalid_binding_is_binding_invalid(self, tmp_path: Path) -> None:
        capture = json_run(tmp_path, '{"auc": 0.87}')
        binding = pointer("auc")  # no leading slash
        assert binding.invalid
        assert cause_of(locate(binding, capture)) == causes.BINDING_INVALID

    def test_an_artifact_the_run_did_not_write_is_no_binding(self, tmp_path: Path) -> None:
        capture = json_run(tmp_path, '{"auc": 0.87}')
        assert cause_of(locate(pointer("/auc", "other.json"), capture)) == causes.NO_BINDING

    def test_a_stale_target_is_stale_and_its_bytes_are_never_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, capture = run_program(
            tmp_path, prints("done\n"), files={"results.json": b'{"auc": 0.87}'}
        )
        assert [s.relpath for s in capture.stale] == ["results.json"]
        reads: list[str] = []
        real_read = Capture.read
        monkeypatch.setattr(
            Capture, "read", lambda self, a: reads.append(a.relpath) or real_read(self, a)
        )
        assert cause_of(locate(pointer("/auc"), capture)) == causes.STALE_ARTIFACT
        assert reads == []

    def test_a_stale_notebook_makes_its_cells_stale_and_never_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cells = [{
            "cell_type": "code", "execution_count": 1, "metadata": {},
            "outputs": [{"output_type": "stream", "name": "stdout", "text": ["0.87\n"]}],
            "source": ["print(0.87)"],
        }]
        capture = stale_cell_capture(tmp_path, cells)
        assert [s.relpath for s in capture.stale] == ["analysis.ipynb"]
        assert any(a.relpath == "analysis.ipynb#cell-0" for a in capture.locatable)
        reads: list[str] = []
        real_read = Capture.read
        monkeypatch.setattr(
            Capture, "read", lambda self, a: reads.append(a.relpath) or real_read(self, a)
        )
        assert cause_of(locate(notebook_cell("/0/text/0"), capture)) == causes.STALE_ARTIFACT
        assert reads == []

    def test_a_tampered_store_raises_rather_than_becoming_a_cause(self, tmp_path: Path) -> None:
        capture = json_run(tmp_path, '{"auc": 0.87}')
        artifact = next(a for a in capture.artifacts if a.relpath == "results.json")
        (capture.store / artifact.sha256).write_bytes(b'{"auc": 0.95}')
        with pytest.raises(ValueError, match="does not match its hash"):
            locate(pointer("/auc"), capture)


class TestFloatRepr:
    """A shortest-repr float is the program's exact double, not a rounding (gate-paper G1)."""

    def test_a_float_repr_binding_locates_with_zero_half_unit(self, tmp_path: Path) -> None:
        raw_bindings = json.dumps({"bindings": [{
            "claim_id": "c", "artifact": "results.json",
            "locator": {"kind": "json_pointer", "pointer": "/ms"}, "float_repr": True,
        }]}).encode()
        binding = load_bindings(raw_bindings, ["c"])["c"]
        located = locate(binding, json_run(tmp_path, '{"ms": 2.5}'))
        assert located.text == "2.5"
        assert located.value == Decimal("2.5")
        assert located.half_unit == 0

    def test_without_the_flag_the_written_digits_are_the_precision(self, tmp_path: Path) -> None:
        located = locate(pointer("/ms"), json_run(tmp_path, '{"ms": 2.5}'))
        assert located.half_unit == Decimal("0.05")
