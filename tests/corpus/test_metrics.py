"""Corpus metrics: coverage, precision, recall and canonical bytes (Phase 1).

Acceptance criteria 1-4 of `docs/planning/discrepancy-corpus/benchmark/spec.md`
and design decisions 1-5 of `benchmark/plan_20261001.md`, written failing
first against `src/plumb/corpus/metrics.py`:

- `read_verdict_rows` is the strict minimal reader of the canonical
  `verdicts.json` (`{run_id, coverage, verdicts}`; each verdict with
  `claim_id`, `verdict`, `bound`): any other shape, a missing key, a wrong
  type, an unknown verdict, or a `bound` flag contradicting its verdict is a
  `ValueError`.
- `case_coverage` counts bound/claims by the C4 bound definition
  (`docs/planning/binding-verdict/prd.md:179-181`): `UNVERIFIED` claims in the
  claims total, never bound, never in any pass/fail rate.
- `store_metrics` computes precision = confirmed/(confirmed+refuted) over the
  labeled `DIVERGED`s — an unlabeled `DIVERGED` is in neither side — and
  recall = confirmed-DIVERGED / labeled claims (any labeled claim is flagged);
  a label keying a claim the case does not carry, or a value outside
  confirmed/refuted, is refused; no labeled `DIVERGED`s is the distinct state
  `None`, never 0/0 and never a bare rate.
- `serialize_metrics` renders the house canonical bytes: sorted keys, no
  incidental whitespace, UTF-8, one trailing newline, authority carried,
  byte-identical across invocations.

The exclusion rules are the honesty of this aspect, so each gets a direct
test and a mutation check (the `test_false_diverged_guard.py` pattern).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plumb.corpus import bank_case, read_case
from plumb.corpus.case import Case
from plumb.corpus.metrics import (
    DIVERGED,
    REPRODUCED,
    UNVERIFIED,
    WITHIN_TOLERANCE,
    CaseMetrics,
    Coverage,
    Metrics,
    Rate,
    Totals,
    VerdictRow,
    case_coverage,
    read_verdict_rows,
    serialize_metrics,
    store_metrics,
)
from plumb.corpus.store import CaseRead
from record_helpers import record_dir

import plumb.corpus.metrics as metrics_module

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}

_AGRODESIGN_VERDICTS = (
    Path(__file__).resolve().parents[2] / "fixtures" / "gate" / "agrodesign" / "verdicts.json"
)


def _rows(*verdicts: tuple[str, str]) -> list[tuple[str, str, bool]]:
    return [(claim_id, verdict, verdict != UNVERIFIED) for claim_id, verdict in verdicts]


def _verdicts_bytes(rows: list[tuple[str, str, bool]], run_id: str = "run-1") -> bytes:
    document = {
        "run_id": run_id,
        "coverage": {
            "claims": len(rows),
            "bound": sum(bound for _, _, bound in rows),
            "by_verdict": {},
            "by_cause": {},
        },
        "verdicts": [
            {"claim_id": claim_id, "verdict": verdict, "bound": bound}
            for claim_id, verdict, bound in rows
        ],
    }
    return (json.dumps(document, **_JSON) + "\n").encode("utf-8")


def _case(
    case_id: str,
    rows: list[tuple[str, str, bool]],
    labels: dict[str, str] | None = None,
) -> CaseRead:
    case = Case(
        format="plumb-corpus-case/1",
        case_id=case_id,
        paper_hash=None,
        run_id="run-1",
        member_hashes={
            "bindings": "0" * 64,
            "claims": "0" * 64,
            "trace": "0" * 64,
            "verdicts": "0" * 64,
        },
        objects_tree_hash="0" * 64,
        has_labels=labels is not None,
        labels_hash=None if labels is None else "0" * 64,
    )
    return CaseRead(
        case=case,
        members={"verdicts": _verdicts_bytes(rows)},
        objects={},
        paper=None,
        labels=labels,
    )


# -----------------------------------------------------------------------------
# read_verdict_rows
# -----------------------------------------------------------------------------


def test_reads_canonical_rows() -> None:
    rows = read_verdict_rows(
        _verdicts_bytes(_rows(("c1", DIVERGED), ("c2", REPRODUCED), ("c3", UNVERIFIED)))
    )
    assert rows == (
        VerdictRow(claim_id="c1", verdict=DIVERGED, bound=True),
        VerdictRow(claim_id="c2", verdict=REPRODUCED, bound=True),
        VerdictRow(claim_id="c3", verdict=UNVERIFIED, bound=False),
    )


def test_reads_the_banked_agrodesign_verdicts() -> None:
    rows = read_verdict_rows(_AGRODESIGN_VERDICTS.read_bytes())
    assert len(rows) == 86
    assert all(row.bound == (row.verdict != UNVERIFIED) for row in rows)
    ids = [row.claim_id for row in rows]
    assert ids == sorted(set(ids))


def test_empty_verdicts_list_reads_as_no_rows() -> None:
    assert read_verdict_rows(_verdicts_bytes([])) == ()


def test_extra_row_keys_are_allowed() -> None:
    document = json.loads(_verdicts_bytes(_rows(("c1", REPRODUCED))).decode("utf-8"))
    document["verdicts"][0].update(
        {
            "artifact": "results/a.csv",
            "located_text": "9.0",
            "sha256": "0" * 64,
            "rederived": "9.0",
            "band": ["8.5", "9.5"],
        }
    )
    rows = read_verdict_rows((json.dumps(document, **_JSON) + "\n").encode("utf-8"))
    assert rows == (VerdictRow(claim_id="c1", verdict=REPRODUCED, bound=True),)


def test_refuses_unparsable_bytes() -> None:
    with pytest.raises(ValueError):
        read_verdict_rows(b"not json at all")


def test_refuses_a_non_object_document() -> None:
    with pytest.raises(ValueError):
        read_verdict_rows(b'["run-1", []]\n')


@pytest.mark.parametrize("missing", ["run_id", "coverage", "verdicts"])
def test_refuses_a_missing_top_level_key(missing: str) -> None:
    document = json.loads(_verdicts_bytes([]).decode("utf-8"))
    del document[missing]
    with pytest.raises(ValueError):
        read_verdict_rows((json.dumps(document, **_JSON) + "\n").encode("utf-8"))


@pytest.mark.parametrize(
    "tweak",
    [
        lambda doc: {**doc, "run_id": 5},
        lambda doc: {**doc, "run_id": None},
        lambda doc: {**doc, "coverage": []},
        lambda doc: {**doc, "coverage": None},
        lambda doc: {**doc, "verdicts": {}},
        lambda doc: {**doc, "verdicts": None},
    ],
)
def test_refuses_a_wrong_typed_top_level_field(tweak) -> None:
    document = json.loads(_verdicts_bytes([]).decode("utf-8"))
    with pytest.raises(ValueError):
        read_verdict_rows((json.dumps(tweak(document), **_JSON) + "\n").encode("utf-8"))


def test_refuses_a_non_object_row() -> None:
    document = json.loads(_verdicts_bytes(_rows(("c1", REPRODUCED))).decode("utf-8"))
    document["verdicts"] = ["REPRODUCED"]
    with pytest.raises(ValueError):
        read_verdict_rows((json.dumps(document, **_JSON) + "\n").encode("utf-8"))


@pytest.mark.parametrize("missing", ["claim_id", "verdict", "bound"])
def test_refuses_a_row_missing_a_required_key(missing: str) -> None:
    document = json.loads(_verdicts_bytes(_rows(("c1", REPRODUCED))).decode("utf-8"))
    del document["verdicts"][0][missing]
    with pytest.raises(ValueError):
        read_verdict_rows((json.dumps(document, **_JSON) + "\n").encode("utf-8"))


@pytest.mark.parametrize(
    "tweak",
    [
        lambda row: {**row, "claim_id": 5},
        lambda row: {**row, "verdict": True},
        lambda row: {**row, "bound": "yes"},
        lambda row: {**row, "bound": 1},
    ],
)
def test_refuses_a_wrong_typed_row_field(tweak) -> None:
    document = json.loads(_verdicts_bytes(_rows(("c1", REPRODUCED))).decode("utf-8"))
    document["verdicts"][0] = tweak(document["verdicts"][0])
    with pytest.raises(ValueError):
        read_verdict_rows((json.dumps(document, **_JSON) + "\n").encode("utf-8"))


def test_refuses_an_unknown_verdict() -> None:
    document = json.loads(_verdicts_bytes(_rows(("c1", REPRODUCED))).decode("utf-8"))
    document["verdicts"][0]["verdict"] = "PASSED"
    with pytest.raises(ValueError):
        read_verdict_rows((json.dumps(document, **_JSON) + "\n").encode("utf-8"))


def test_refuses_an_unverified_claim_marked_bound() -> None:
    document = json.loads(_verdicts_bytes(_rows(("c1", UNVERIFIED))).decode("utf-8"))
    document["verdicts"][0]["bound"] = True
    with pytest.raises(ValueError):
        read_verdict_rows((json.dumps(document, **_JSON) + "\n").encode("utf-8"))


def test_refuses_a_decided_claim_marked_unbound() -> None:
    document = json.loads(_verdicts_bytes(_rows(("c1", REPRODUCED))).decode("utf-8"))
    document["verdicts"][0]["bound"] = False
    with pytest.raises(ValueError):
        read_verdict_rows((json.dumps(document, **_JSON) + "\n").encode("utf-8"))


# -----------------------------------------------------------------------------
# case_coverage
# -----------------------------------------------------------------------------


def test_counts_claims_and_bound() -> None:
    coverage = case_coverage(
        (
            VerdictRow(claim_id="c1", verdict=DIVERGED, bound=True),
            VerdictRow(claim_id="c2", verdict=REPRODUCED, bound=True),
            VerdictRow(claim_id="c3", verdict=WITHIN_TOLERANCE, bound=True),
            VerdictRow(claim_id="c4", verdict=REPRODUCED, bound=True),
            VerdictRow(claim_id="c5", verdict=UNVERIFIED, bound=False),
        )
    )
    assert coverage.claims == 5
    assert coverage.bound == 4


def test_unverified_claims_count_in_claims_and_never_bound() -> None:
    coverage = case_coverage(
        (
            VerdictRow(claim_id="c1", verdict=UNVERIFIED, bound=False),
            VerdictRow(claim_id="c2", verdict=REPRODUCED, bound=True),
            VerdictRow(claim_id="c3", verdict=UNVERIFIED, bound=False),
        )
    )
    assert coverage.claims == 3
    assert coverage.bound == 1
    by_verdict = dict(coverage.by_verdict)
    assert by_verdict[UNVERIFIED] == 2


def test_by_verdict_is_pinned_in_c4_order() -> None:
    coverage = case_coverage(
        (
            VerdictRow(claim_id="c1", verdict=DIVERGED, bound=True),
            VerdictRow(claim_id="c2", verdict=REPRODUCED, bound=True),
            VerdictRow(claim_id="c3", verdict=WITHIN_TOLERANCE, bound=True),
            VerdictRow(claim_id="c4", verdict=UNVERIFIED, bound=False),
        )
    )
    assert coverage.by_verdict == (
        (REPRODUCED, 1),
        (WITHIN_TOLERANCE, 1),
        (DIVERGED, 1),
        (UNVERIFIED, 1),
    )


def test_empty_rows_coverage_is_zero() -> None:
    coverage = case_coverage(())
    assert coverage.claims == 0
    assert coverage.bound == 0
    assert coverage.by_verdict == (
        (REPRODUCED, 0),
        (WITHIN_TOLERANCE, 0),
        (DIVERGED, 0),
        (UNVERIFIED, 0),
    )


# -----------------------------------------------------------------------------
# store_metrics
# -----------------------------------------------------------------------------

_MIXED = [
    ("c1", DIVERGED),
    ("c2", DIVERGED),
    ("c3", DIVERGED),
    ("c4", REPRODUCED),
    ("c5", UNVERIFIED),
]
_MIXED_LABELS = {"c1": "confirmed", "c2": "refuted", "c4": "confirmed"}


def test_precision_is_confirmed_over_confirmed_plus_refuted() -> None:
    metrics = store_metrics([_case("a", _rows(*_MIXED), labels=_MIXED_LABELS)])
    case_metrics = metrics.cases[0]
    assert case_metrics.diverged == 3
    assert case_metrics.confirmed == 1
    assert case_metrics.refuted == 1
    assert case_metrics.precision == Rate(confirmed=1, flagged=2)


def test_an_unlabeled_diverged_is_in_neither_side() -> None:
    metrics = store_metrics([_case("a", _rows(*_MIXED), labels=_MIXED_LABELS)])
    assert metrics.totals.diverged == 3
    assert metrics.totals.confirmed == 1
    assert metrics.totals.refuted == 1
    assert metrics.totals.precision == Rate(confirmed=1, flagged=2)


def test_recall_counts_every_labeled_claim_as_flagged() -> None:
    metrics = store_metrics([_case("a", _rows(*_MIXED), labels=_MIXED_LABELS)])
    case_metrics = metrics.cases[0]
    assert case_metrics.labeled == 3
    assert case_metrics.recall == Rate(confirmed=1, flagged=3)


def test_an_unlabeled_case_has_no_rates() -> None:
    metrics = store_metrics([_case("a", _rows(*_MIXED))])
    case_metrics = metrics.cases[0]
    assert case_metrics.labeled == 0
    assert case_metrics.confirmed == 0
    assert case_metrics.refuted == 0
    assert case_metrics.precision is None
    assert case_metrics.recall is None


def test_no_labeled_diverged_is_a_distinct_state() -> None:
    case = _case("a", _rows(("c1", REPRODUCED), ("c2", UNVERIFIED)), labels={"c1": "confirmed"})
    metrics = store_metrics([case])
    case_metrics = metrics.cases[0]
    assert case_metrics.diverged == 0
    assert case_metrics.precision is None
    assert case_metrics.recall == Rate(confirmed=0, flagged=1)


def test_a_label_keying_an_unknown_claim_is_refused() -> None:
    case = _case("a", _rows(("c1", REPRODUCED)), labels={"ghost": "confirmed"})
    with pytest.raises(ValueError):
        store_metrics([case])


def test_a_label_value_outside_confirmed_refuted_is_refused() -> None:
    case = _case("a", _rows(("c1", REPRODUCED)), labels={"c1": "wrong"})
    with pytest.raises(ValueError):
        store_metrics([case])


def test_totals_pool_precision_across_cases() -> None:
    first = _case("a", _rows(("c1", DIVERGED)), labels={"c1": "confirmed"})
    second = _case("b", _rows(("c2", DIVERGED), ("c3", DIVERGED)), labels={"c2": "refuted"})
    metrics = store_metrics([first, second])
    assert metrics.totals.cases == 2
    assert metrics.totals.coverage.claims == 3
    assert metrics.totals.coverage.bound == 3
    assert metrics.totals.diverged == 3
    assert metrics.totals.labeled == 2
    assert metrics.totals.confirmed == 1
    assert metrics.totals.refuted == 1
    assert metrics.totals.precision == Rate(confirmed=1, flagged=2)
    assert metrics.totals.recall == Rate(confirmed=1, flagged=2)


def test_an_empty_store_totals_carry_zeros_and_no_rates() -> None:
    metrics = store_metrics([])
    assert metrics.cases == ()
    assert metrics.totals.cases == 0
    assert metrics.totals.coverage.claims == 0
    assert metrics.totals.coverage.bound == 0
    assert metrics.totals.diverged == 0
    assert metrics.totals.labeled == 0
    assert metrics.totals.confirmed == 0
    assert metrics.totals.refuted == 0
    assert metrics.totals.precision is None
    assert metrics.totals.recall is None


def test_cases_are_sorted_by_case_id() -> None:
    metrics = store_metrics(
        [
            _case("z", _rows(("c1", REPRODUCED))),
            _case("a", _rows(("c2", REPRODUCED))),
            _case("m", _rows(("c3", REPRODUCED))),
        ]
    )
    assert [case_metrics.case_id for case_metrics in metrics.cases] == ["a", "m", "z"]


def test_a_banked_record_with_labels_produces_metrics(tmp_path: Path) -> None:
    record = record_dir(tmp_path / "record")
    (record / "verdicts.json").write_bytes(
        _verdicts_bytes(_rows(("c1", DIVERGED), ("c2", REPRODUCED)))
    )
    case = bank_case(record, tmp_path / "store", labels={"c1": "confirmed", "c2": "refuted"})
    got = read_case(tmp_path / "store" / case.case_id)
    metrics = store_metrics([got])
    assert metrics.cases[0].case_id == case.case_id
    assert metrics.totals.coverage.claims == 2
    assert metrics.totals.coverage.bound == 2
    assert metrics.totals.diverged == 1
    assert metrics.totals.confirmed == 1
    assert metrics.totals.precision == Rate(confirmed=1, flagged=1)
    assert metrics.totals.recall == Rate(confirmed=1, flagged=2)


# -----------------------------------------------------------------------------
# serialize_metrics
# -----------------------------------------------------------------------------


def test_bytes_are_canonical_and_exact() -> None:
    metrics = store_metrics([_case("a", _rows(*_MIXED), labels=_MIXED_LABELS)])
    expected = (
        '{"authority":"owner","cases":[{"case_id":"a","confirmed":1,'
        '"coverage":{"bound":4,"by_verdict":[["REPRODUCED",1],'
        '["WITHIN-TOLERANCE",0],["DIVERGED",3],["UNVERIFIED",1]],"claims":5},'
        '"diverged":3,"labeled":3,"precision":{"confirmed":1,"flagged":2},'
        '"recall":{"confirmed":1,"flagged":3},"refuted":1}],"totals":'
        '{"cases":1,"confirmed":1,"coverage":{"bound":4,"by_verdict":'
        '[["REPRODUCED",1],["WITHIN-TOLERANCE",0],["DIVERGED",3],'
        '["UNVERIFIED",1]],"claims":5},"diverged":3,"labeled":3,'
        '"precision":{"confirmed":1,"flagged":2},"recall":{"confirmed":1,'
        '"flagged":3},"refuted":1}}\n'
    ).encode("utf-8")
    assert serialize_metrics(metrics, "owner") == expected


def test_authority_is_carried_in_the_bytes() -> None:
    metrics = store_metrics([_case("a", _rows(("c1", REPRODUCED)))])
    assert b'"authority":"owner"' in serialize_metrics(metrics, "owner")
    assert b'"authority":"third-party"' in serialize_metrics(metrics, "third-party")


def test_two_serializations_are_byte_identical() -> None:
    metrics = store_metrics([_case("a", _rows(*_MIXED), labels=_MIXED_LABELS)])
    assert serialize_metrics(metrics, "owner") == serialize_metrics(metrics, "owner")
    reordered = store_metrics(
        [
            _case("m", _rows(("c1", REPRODUCED))),
            _case("a", _rows(*_MIXED), labels=_MIXED_LABELS),
        ]
    )
    stable = store_metrics(
        [
            _case("a", _rows(*_MIXED), labels=_MIXED_LABELS),
            _case("m", _rows(("c1", REPRODUCED))),
        ]
    )
    assert serialize_metrics(reordered, "owner") == serialize_metrics(stable, "owner")


def test_no_labeled_diverged_serializes_as_null() -> None:
    case = _case("a", _rows(("c1", REPRODUCED), ("c2", UNVERIFIED)), labels={"c1": "confirmed"})
    out = serialize_metrics(store_metrics([case]), "owner")
    assert b'"precision":null' in out
    assert b'"precision":{"confirmed":0,"flagged":0}' not in out
    assert b'"recall":{"confirmed":0,"flagged":1}' in out


def test_an_unlabeled_case_serializes_null_rates() -> None:
    out = serialize_metrics(store_metrics([_case("a", _rows(("c1", REPRODUCED)))]), "owner")
    assert b'"precision":null' in out
    assert b'"recall":null' in out


def test_an_empty_store_serializes_zeros_and_null_rates() -> None:
    out = serialize_metrics(store_metrics([]), "owner")
    assert b'"cases":[],"totals":{"cases":0,"confirmed":0,"coverage":{"bound":0,' in out
    assert b'"precision":null' in out
    assert out.endswith(b"}\n")


# -----------------------------------------------------------------------------
# Mutation checks: the exclusion rules are the honesty of this aspect
# -----------------------------------------------------------------------------


def _assert_unlabeled_diverged_excluded() -> Metrics:
    case = _case(
        "a",
        _rows(("c1", DIVERGED), ("c2", DIVERGED), ("c3", DIVERGED)),
        labels={"c1": "confirmed", "c2": "refuted"},
    )
    metrics = store_metrics([case])
    assert metrics.totals.confirmed == 1, "unlabeled DIVERGED leaked into confirmed"
    assert (
        metrics.totals.precision == Rate(confirmed=1, flagged=2)
    ), "unlabeled DIVERGED counted in the denominator"
    return metrics


def _assert_no_labeled_diverged_is_not_a_rate() -> Metrics:
    case = _case("a", _rows(("c1", REPRODUCED)), labels={"c1": "confirmed"})
    metrics = store_metrics([case])
    assert metrics.totals.precision is None, "no labeled DIVERGEDs must not be a rate"
    assert b'"precision":null' in serialize_metrics(metrics, "owner")
    return metrics


class TestMutations:
    def test_removing_the_unlabeled_exclusion_breaks_precision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def sloppy(rows, labels):
            confirmed = 0
            refuted = 0
            for row in rows:
                if row.verdict != DIVERGED:
                    continue
                if labels is not None and labels.get(row.claim_id) == "confirmed":
                    confirmed += 1
                else:
                    refuted += 1
            return confirmed, refuted

        monkeypatch.setattr(metrics_module, "_labeled_diverged", sloppy)
        with pytest.raises(AssertionError, match="unlabeled"):
            _assert_unlabeled_diverged_excluded()

    def test_removing_the_no_rate_state_breaks_the_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def always_a_rate(confirmed, refuted):
            return Rate(confirmed, refuted)

        monkeypatch.setattr(metrics_module, "_precision", always_a_rate)
        monkeypatch.setattr(metrics_module, "_recall", always_a_rate)
        with pytest.raises(AssertionError, match="no labeled DIVERGEDs"):
            _assert_no_labeled_diverged_is_not_a_rate()