"""Locating a bound value in what the run actually produced (M2).

`locate(binding, capture)` returns the verbatim located text, its strict
`Decimal`, its written precision, and the artifact's hash — or a named cause.
Bytes are read only through `Capture.read` (hash re-checked), and a stale
output's bytes are never read at all (`CLAUDE.md` #5).
"""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

import pytest

from plumb.run.capture import Capture
from plumb.verify import causes
from plumb.verify.bindings import load_bindings
from plumb.verify.locate import Located, Unlocated, locate
from verify_helpers import prints, run_program, writes


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


def json_run(tmp_path: Path, text: str) -> Capture:
    return run_program(tmp_path, writes("results.json", text))[1]


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

    def test_a_tampered_store_raises_rather_than_becoming_a_cause(self, tmp_path: Path) -> None:
        capture = json_run(tmp_path, '{"auc": 0.87}')
        artifact = next(a for a in capture.artifacts if a.relpath == "results.json")
        (capture.store / artifact.sha256).write_bytes(b'{"auc": 0.95}')
        with pytest.raises(ValueError, match="does not match its hash"):
            locate(pointer("/auc"), capture)
