"""The bindings file: which captured value each claim is checked against (M1).

A binding is written by the user, so the file is read strictly. Anything that
makes the *file* untrustworthy — bad JSON, an unknown field, a binding to a
claim that does not exist, a tolerance written as a JSON number (it would have
passed through a float) — raises `BindingInvalid` and nothing is verified. A
single entry whose locator is unusable only makes that one claim
`UNVERIFIED: BINDING_INVALID`; the rest of the file still counts.
"""

from __future__ import annotations

from decimal import Decimal
import json

import pytest

from plumb.verify.bindings import CsvCell, JsonPointer, StdoutRegex, load_bindings
from plumb.verify.causes import BindingInvalid
from plumb.verify.numbers import Tolerance

IDS = ("c-auc", "c-p", "c-acc")


def raw(*entries: dict, top: dict | None = None) -> bytes:
    return json.dumps(top if top is not None else {"bindings": list(entries)}).encode()


def entry(claim_id: str = "c-auc", **overrides) -> dict:
    base = {
        "claim_id": claim_id,
        "artifact": "results.json",
        "locator": {"kind": "json_pointer", "pointer": "/metrics/auc"},
    }
    base.update(overrides)
    return base


class TestValidFile:
    def test_one_entry_per_locator_kind_loads(self) -> None:
        bindings = load_bindings(
            raw(
                entry("c-auc", tolerance={"abs": "0.01"}),
                entry(
                    "c-p",
                    artifact="<stdout>",
                    locator={"kind": "stdout_regex", "pattern": r"p = (\S+)"},
                ),
                entry(
                    "c-acc",
                    artifact="out/table.csv",
                    locator={"kind": "csv_cell", "column": "acc", "row": {"model": "A"}},
                    scale="100",
                ),
            ),
            IDS,
        )
        assert list(bindings) == ["c-acc", "c-auc", "c-p"]
        assert bindings["c-auc"].locator == JsonPointer("/metrics/auc")
        assert bindings["c-auc"].tolerance == Tolerance("abs", Decimal("0.01"))
        assert bindings["c-auc"].scale is None
        assert bindings["c-p"].locator == StdoutRegex(r"p = (\S+)")
        assert bindings["c-acc"].locator == CsvCell("acc", (("model", "A"),))
        assert bindings["c-acc"].scale == Decimal("100")
        assert all(b.invalid is None for b in bindings.values())

    def test_a_relative_tolerance_loads(self) -> None:
        bindings = load_bindings(raw(entry(tolerance={"rel": "0.05"})), IDS)
        assert bindings["c-auc"].tolerance == Tolerance("rel", Decimal("0.05"))

    def test_claims_without_a_binding_are_simply_absent(self) -> None:
        assert set(load_bindings(raw(entry()), IDS)) == {"c-auc"}

    def test_the_bindings_are_read_only(self) -> None:
        bindings = load_bindings(raw(entry()), IDS)
        with pytest.raises(TypeError):
            bindings["c-p"] = bindings["c-auc"]  # type: ignore[index]


class TestWholeFileRefusals:
    @pytest.mark.parametrize(
        ("data", "why"),
        [
            (b"\xff\xfe", "not UTF-8"),
            (b"{not json", "not JSON"),
            (b"[]", "top level not an object"),
            (raw(top={"bindings": [], "extra": 1}), "unknown top-level field"),
            (raw(top={}), "no bindings field"),
            (raw(top={"bindings": {}}), "bindings not a list"),
            (raw(top={"bindings": ["x"]}), "entry not an object"),
            (raw(entry(note="hi")), "unknown entry field"),
            (raw({"artifact": "a.json", "locator": {"kind": "json_pointer", "pointer": ""}}),
             "no claim_id"),
            (raw(entry(claim_id=3)), "claim_id not a string"),
            (raw(entry(), entry()), "duplicate claim_id"),
            (raw(entry("c-unknown")), "claim_id not among the claims"),
            (raw(entry(artifact="<stderr>")), "stderr is diagnostic-only"),
            (raw(entry(artifact=7)), "artifact not a string"),
            (raw(entry(locator={"kind": "xpath", "path": "//a"})), "unknown locator kind"),
            (raw(entry(locator={"kind": "json_pointer"})), "locator missing its field"),
            (raw(entry(locator={"kind": "json_pointer", "pointer": "/a", "x": 1})),
             "locator extra field"),
            (raw(entry(locator={"kind": "csv_cell", "column": "a", "row": {"k": 1}})),
             "csv row value not a string"),
            (raw(entry(tolerance={"abs": 0.01})), "JSON-number tolerance"),
            (raw(entry(tolerance={"abs": "0.01", "rel": "0.1"})), "two tolerance kinds"),
            (raw(entry(tolerance={"pct": "1"})), "unknown tolerance kind"),
            (raw(entry(tolerance={"abs": "-0.01"})), "negative tolerance"),
            (raw(entry(tolerance={"abs": "1,000"})), "tolerance not a strict decimal"),
            (raw(entry(scale=100)), "JSON-number scale"),
            (raw(entry(scale="0")), "zero scale"),
            (raw(entry(scale="-1")), "negative scale"),
            (b'{"bindings": [{"claim_id": "c-auc", "claim_id": "c-p"}]}', "duplicate key"),
            (b'{"bindings": NaN}', "NaN constant"),
        ],
    )
    def test_raises_binding_invalid(self, data: bytes, why: str) -> None:
        with pytest.raises(BindingInvalid):
            load_bindings(data, IDS)

    def test_the_message_names_the_offending_claim(self) -> None:
        with pytest.raises(BindingInvalid, match="c-unknown"):
            load_bindings(raw(entry("c-unknown")), IDS)

    def test_duplicate_ids_in_the_claim_set_are_refused(self) -> None:
        with pytest.raises(BindingInvalid):
            load_bindings(raw(entry()), ("c-auc", "c-auc"))


class TestPerEntryInvalid:
    """An unusable locator marks only its own claim; the file still loads."""

    @pytest.mark.parametrize(
        ("overrides", "why"),
        [
            ({"locator": {"kind": "json_pointer", "pointer": "metrics/auc"}}, "no leading /"),
            ({"locator": {"kind": "json_pointer", "pointer": "/a~2b"}}, "bad ~ escape"),
            ({"locator": {"kind": "json_pointer", "pointer": "/a~"}}, "trailing ~"),
            ({"artifact": "<stdout>", "locator": {"kind": "stdout_regex", "pattern": "("}},
             "regex does not compile"),
            ({"artifact": "<stdout>", "locator": {"kind": "stdout_regex", "pattern": r"\d+"}},
             "regex without a group"),
            ({"artifact": "<stdout>",
              "locator": {"kind": "stdout_regex", "pattern": r"(\d+)\.(\d+)"}},
             "regex with two groups"),
            ({"artifact": "t.csv", "locator": {"kind": "csv_cell", "column": "a", "row": {}}},
             "csv row with no key"),
            ({"artifact": "t.csv",
              "locator": {"kind": "csv_cell", "column": "a", "row": {"k": "1", "j": "2"}}},
             "csv row with two keys"),
            ({"artifact": "results.csv"}, "json pointer on a csv"),
            ({"artifact": "<stdout>"}, "json pointer on stdout"),
            ({"locator": {"kind": "stdout_regex", "pattern": "(x)"}}, "regex on a file"),
            ({"locator": {"kind": "csv_cell", "column": "a", "row": {"k": "1"}}},
             "csv cell on a json"),
        ],
    )
    def test_marks_the_entry_invalid(self, overrides: dict, why: str) -> None:
        bindings = load_bindings(raw(entry(**overrides), entry("c-p")), IDS)
        assert bindings["c-auc"].invalid, why
        assert bindings["c-p"].invalid is None

    def test_a_valid_pointer_with_escapes_is_valid(self) -> None:
        bindings = load_bindings(
            raw(entry(locator={"kind": "json_pointer", "pointer": "/a~1b/~0c/0"})), IDS
        )
        assert bindings["c-auc"].invalid is None

    def test_the_empty_pointer_is_valid(self) -> None:
        bindings = load_bindings(raw(entry(locator={"kind": "json_pointer", "pointer": ""})), IDS)
        assert bindings["c-auc"].invalid is None


class TestFloatRepr:
    """`float_repr` declares the artifact wrote shortest round-trip floats (gate-paper G1)."""

    def test_it_defaults_to_false(self) -> None:
        assert load_bindings(raw(entry()), IDS)["c-auc"].float_repr is False

    def test_it_loads_as_true(self) -> None:
        assert load_bindings(raw(entry(float_repr=True)), IDS)["c-auc"].float_repr is True

    @pytest.mark.parametrize("value", ["true", 1, None])
    def test_a_non_boolean_is_refused(self, value) -> None:
        with pytest.raises(BindingInvalid, match="float_repr"):
            load_bindings(raw(entry(float_repr=value)), IDS)
