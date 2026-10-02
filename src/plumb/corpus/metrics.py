"""Coverage, precision and recall over banked cases — the benchmark math (Phase 1).

`read_verdict_rows` is the strict minimal reader of the canonical
`verdicts.json` (`{run_id, coverage, verdicts}`, each verdict with `claim_id`,
`verdict`, `bound`): any other shape, a missing key, a wrong type, an unknown
verdict, or a `bound` flag contradicting its verdict is refused with a
`ValueError` — the caller's named-cause path. `case_coverage` counts bound and
claims by the C4 bound definition (`docs/planning/binding-verdict/prd.md`): a
claim is bound when a value was located and parsed, whatever the verdict;
`UNVERIFIED` claims count in the claims total and are never bound.

`store_metrics` folds each case's verdicts and its verified labels into
per-case counts and pooled totals: precision is confirmed/(confirmed+refuted)
over the labeled `DIVERGED`s — an unlabeled `DIVERGED` is in neither side —
and recall is confirmed-DIVERGEDs over labeled claims (any labeled claim
counts as flagged). A label keying a claim the case does not carry, or a
value that is not confirmed/refuted, is refused. With no labeled `DIVERGED`
the precision is the distinct state `None` — never 0/0 and never a bare rate.
`serialize_metrics` renders the house canonical bytes: sorted keys, no
incidental whitespace, UTF-8 without escapes, one trailing newline, and the
label-authority declaration carried in the document.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from typing import Any

from plumb.corpus.store import CaseRead

__all__ = [
    "CONFIRMED",
    "DIVERGED",
    "REPRODUCED",
    "REFUTED",
    "UNVERIFIED",
    "WITHIN_TOLERANCE",
    "CaseMetrics",
    "Coverage",
    "Metrics",
    "Rate",
    "Totals",
    "VerdictRow",
    "case_coverage",
    "read_verdict_rows",
    "serialize_metrics",
    "store_metrics",
]

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}

REPRODUCED = "REPRODUCED"
WITHIN_TOLERANCE = "WITHIN-TOLERANCE"
DIVERGED = "DIVERGED"
UNVERIFIED = "UNVERIFIED"

#: The verdict vocabulary in the C4 coverage order — the order `by_verdict` pins.
_VERDICTS = (REPRODUCED, WITHIN_TOLERANCE, DIVERGED, UNVERIFIED)

CONFIRMED = "confirmed"
REFUTED = "refuted"
_LABEL_VALUES = (CONFIRMED, REFUTED)


@dataclass(frozen=True, slots=True)
class VerdictRow:
    """One verdict as the metrics read it: the three fields metrics needs."""

    claim_id: str
    verdict: str
    bound: bool


@dataclass(frozen=True, slots=True)
class Coverage:
    """A case's (or the store's) coverage: bound and claims by the C4 definition."""

    claims: int
    bound: int
    by_verdict: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class Rate:
    """A rate with its denominator shown: confirmed / flagged.

    For precision, `flagged` is the labeled `DIVERGED`s; for recall, the
    labeled claims. One record serves both figures, disambiguated by the
    parent key in the serialized document.
    """

    confirmed: int
    flagged: int


@dataclass(frozen=True, slots=True)
class CaseMetrics:
    """One case's counts and rates; a `None` rate means no such figure exists."""

    case_id: str
    coverage: Coverage
    diverged: int
    labeled: int
    confirmed: int
    refuted: int
    precision: Rate | None
    recall: Rate | None


@dataclass(frozen=True, slots=True)
class Totals:
    """Store-level sums; denominators always present."""

    cases: int
    coverage: Coverage
    diverged: int
    labeled: int
    confirmed: int
    refuted: int
    precision: Rate | None
    recall: Rate | None


@dataclass(frozen=True, slots=True)
class Metrics:
    """The store's metrics: per-case records sorted by case_id, plus totals."""

    cases: tuple[CaseMetrics, ...]
    totals: Totals


def read_verdict_rows(data: bytes) -> tuple[VerdictRow, ...]:
    """The verdicts of a canonical `verdicts.json`, strictly read.

    The document must be `{run_id, coverage, verdicts}` and every verdict must
    carry a string `claim_id`, a string `verdict` from the C4 vocabulary, and
    a bool `bound` consistent with its verdict — `UNVERIFIED` is never bound.
    Anything else is a `ValueError`.
    """
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"verdicts.json does not parse: {exc}") from None
    if not isinstance(document, dict):
        raise ValueError("verdicts.json is not an object")
    for key, kind in (("run_id", str), ("coverage", dict), ("verdicts", list)):
        if not isinstance(document.get(key), kind):
            raise ValueError(f"verdicts.json must carry {key!r} as a {kind.__name__}")
    return tuple(_verdict_row(item, index) for index, item in enumerate(document["verdicts"]))


def case_coverage(rows: Iterable[VerdictRow]) -> Coverage:
    """Bound and claims by the C4 bound definition; `UNVERIFIED` never bound."""
    counts = {verdict: 0 for verdict in _VERDICTS}
    claims = 0
    bound = 0
    for row in rows:
        claims += 1
        if row.bound:
            bound += 1
        counts[row.verdict] += 1
    return Coverage(
        claims=claims,
        bound=bound,
        by_verdict=tuple((verdict, counts[verdict]) for verdict in _VERDICTS),
    )


def store_metrics(cases: Iterable[CaseRead]) -> Metrics:
    """Per-case metrics sorted by case_id, and pooled totals.

    Precision is confirmed/(confirmed+refuted) over labeled `DIVERGED`s — an
    unlabeled `DIVERGED` is in neither side; recall is confirmed/labeled
    claims. A label keying a claim the case does not carry, or a value other
    than confirmed/refuted, is refused.
    """
    per_case = [_metrics_for(case_read) for case_read in cases]
    per_case.sort(key=lambda case_metrics: case_metrics.case_id)
    return Metrics(cases=tuple(per_case), totals=_totals(tuple(per_case)))


def serialize_metrics(metrics: Metrics, authority: str) -> bytes:
    """The metrics as one canonical JSON line: sorted keys, one trailing newline.

    `authority` is the label-authority declaration (`owner` or `third-party`
    at the CLI) and is carried in the document next to every figure.
    """
    if not isinstance(authority, str) or not authority:
        raise ValueError("authority must be a non-empty string")
    document = {
        "authority": authority,
        "cases": [_case_document(case_metrics) for case_metrics in metrics.cases],
        "totals": _totals_document(metrics.totals),
    }
    return (json.dumps(document, **_JSON) + "\n").encode("utf-8")


def _metrics_for(case_read: CaseRead) -> CaseMetrics:
    rows = read_verdict_rows(case_read.members["verdicts"])
    labels = case_read.labels
    if labels is not None:
        _validate_labels(case_read.case.case_id, rows, labels)
    confirmed, refuted = _labeled_diverged(rows, labels)
    labeled = 0 if labels is None else len(labels)
    return CaseMetrics(
        case_id=case_read.case.case_id,
        coverage=case_coverage(rows),
        diverged=sum(1 for row in rows if row.verdict == DIVERGED),
        labeled=labeled,
        confirmed=confirmed,
        refuted=refuted,
        precision=_precision(confirmed, refuted),
        recall=_recall(confirmed, labeled),
    )


def _validate_labels(
    case_id: str, rows: tuple[VerdictRow, ...], labels: Mapping[str, str]
) -> None:
    """Refuse a label that keys no claim, or a value outside confirmed/refuted."""
    ids = {row.claim_id for row in rows}
    for claim_id, value in labels.items():
        if claim_id not in ids:
            raise ValueError(f"case {case_id}: label {claim_id!r} keys no claim in the case")
        if value not in _LABEL_VALUES:
            raise ValueError(
                f"case {case_id}: label {claim_id!r} has value {value!r}, "
                "expected confirmed or refuted"
            )


def _labeled_diverged(
    rows: tuple[VerdictRow, ...], labels: Mapping[str, str] | None
) -> tuple[int, int]:
    """(confirmed, refuted) over the labeled `DIVERGED`s; unlabeled never counted."""
    confirmed = 0
    refuted = 0
    if labels is None:
        return confirmed, refuted
    by_id = {row.claim_id: row.verdict for row in rows}
    for claim_id, value in labels.items():
        if by_id[claim_id] == DIVERGED:
            if value == CONFIRMED:
                confirmed += 1
            else:
                refuted += 1
    return confirmed, refuted


def _precision(confirmed: int, refuted: int) -> Rate | None:
    flagged = confirmed + refuted
    if flagged == 0:
        return None
    return Rate(confirmed=confirmed, flagged=flagged)


def _recall(confirmed: int, labeled: int) -> Rate | None:
    if labeled == 0:
        return None
    return Rate(confirmed=confirmed, flagged=labeled)


def _totals(per_case: tuple[CaseMetrics, ...]) -> Totals:
    by_verdict = tuple(
        (verdict, sum(case_metrics.coverage.by_verdict[index][1] for case_metrics in per_case))
        for index, verdict in enumerate(_VERDICTS)
    )
    confirmed = sum(case_metrics.confirmed for case_metrics in per_case)
    refuted = sum(case_metrics.refuted for case_metrics in per_case)
    labeled = sum(case_metrics.labeled for case_metrics in per_case)
    return Totals(
        cases=len(per_case),
        coverage=Coverage(
            claims=sum(case_metrics.coverage.claims for case_metrics in per_case),
            bound=sum(case_metrics.coverage.bound for case_metrics in per_case),
            by_verdict=by_verdict,
        ),
        diverged=sum(case_metrics.diverged for case_metrics in per_case),
        labeled=labeled,
        confirmed=confirmed,
        refuted=refuted,
        precision=_precision(confirmed, refuted),
        recall=_recall(confirmed, labeled),
    )


def _case_document(case_metrics: CaseMetrics) -> dict[str, Any]:
    return {
        "case_id": case_metrics.case_id,
        "coverage": _coverage_document(case_metrics.coverage),
        "confirmed": case_metrics.confirmed,
        "diverged": case_metrics.diverged,
        "labeled": case_metrics.labeled,
        "precision": _rate_document(case_metrics.precision),
        "recall": _rate_document(case_metrics.recall),
        "refuted": case_metrics.refuted,
    }


def _totals_document(totals: Totals) -> dict[str, Any]:
    return {
        "cases": totals.cases,
        "coverage": _coverage_document(totals.coverage),
        "confirmed": totals.confirmed,
        "diverged": totals.diverged,
        "labeled": totals.labeled,
        "precision": _rate_document(totals.precision),
        "recall": _rate_document(totals.recall),
        "refuted": totals.refuted,
    }


def _coverage_document(coverage: Coverage) -> dict[str, Any]:
    return {
        "bound": coverage.bound,
        "by_verdict": [list(pair) for pair in coverage.by_verdict],
        "claims": coverage.claims,
    }


def _rate_document(rate: Rate | None) -> dict[str, int] | None:
    if rate is None:
        return None
    return {"confirmed": rate.confirmed, "flagged": rate.flagged}


def _verdict_row(item: object, index: int) -> VerdictRow:
    if not isinstance(item, dict):
        raise ValueError(f"verdicts[{index}] is not an object")
    claim_id = item.get("claim_id")
    verdict = item.get("verdict")
    bound = item.get("bound")
    if not isinstance(claim_id, str):
        raise ValueError(f"verdicts[{index}] must carry a string claim_id")
    if not isinstance(verdict, str):
        raise ValueError(f"verdicts[{index}] must carry a string verdict")
    if not isinstance(bound, bool):
        raise ValueError(f"verdicts[{index}] must carry a bool bound")
    if verdict not in _VERDICTS:
        raise ValueError(f"verdicts[{index}]: unknown verdict {verdict!r}")
    if bound != (verdict != UNVERIFIED):
        raise ValueError(
            f"verdicts[{index}]: claim {claim_id!r} bound does not match its verdict"
        )
    return VerdictRow(claim_id=claim_id, verdict=verdict, bound=bound)