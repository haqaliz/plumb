"""The Verdict record refuses a verdict without its evidence (M5, M6; D5).

The record is the last line of defence for the contract: whatever code builds
one, a `REPRODUCED`, `WITHIN-TOLERANCE` or `DIVERGED` cannot exist unless it
carries the value the run wrote, the hash of the artifact it came from, the run
it came from, and the band or threshold that decided it. An `UNVERIFIED` must
name a cause from the closed vocabulary, and nothing else may carry one.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from plumb.verify import causes
from plumb.verify.bindings import JsonPointer
from plumb.verify.compare import DIVERGED, REPRODUCED, UNVERIFIED, WITHIN_TOLERANCE
from plumb.verify.verdict import Verdict, VerdictSet

D = Decimal

EVIDENCE = dict(
    claim_id="c1",
    reported_text="0.87",
    artifact="results.json",
    locator=JsonPointer("/auc"),
    located_text="0.8712",
    sha256="ab" * 32,
    run_id="cd" * 32,
    rederived=D("0.8712"),
    band=(D("0.865"), D("0.875")),
    tolerance_band=None,
    threshold=None,
    tolerance_threshold=None,
    delta=D("0.0012"),
)


def reproduced(**overrides) -> Verdict:
    return Verdict(**{"verdict": REPRODUCED, "cause": None, **EVIDENCE, **overrides})


def unverified(cause: str, **overrides) -> Verdict:
    bare = {key: None for key in EVIDENCE} | {"claim_id": "c1", "reported_text": "0.87"}
    return Verdict(verdict=UNVERIFIED, cause=cause, **{**bare, **overrides})


def test_a_fully_evidenced_verdict_is_accepted() -> None:
    verdict = reproduced()
    assert verdict.verdict == REPRODUCED
    assert verdict.bound
    assert not verdict.review_required


def test_diverged_requires_review() -> None:
    assert reproduced(verdict=DIVERGED).review_required


def test_review_required_is_derived_not_supplied() -> None:
    with pytest.raises(TypeError):
        Verdict(verdict=DIVERGED, cause=None, review_required=False, **EVIDENCE)  # type: ignore[call-arg]


@pytest.mark.parametrize("verdict", [REPRODUCED, WITHIN_TOLERANCE, DIVERGED])
@pytest.mark.parametrize(
    "missing", ["located_text", "sha256", "run_id", "rederived", "delta", "artifact", "locator"]
)
def test_a_decided_verdict_without_its_evidence_is_refused(verdict: str, missing: str) -> None:
    extra = {"tolerance_band": (D("0.82"), D("0.92"))} if verdict == WITHIN_TOLERANCE else {}
    with pytest.raises(ValueError, match=missing):
        reproduced(verdict=verdict, **extra, **{missing: None})


def test_a_decided_verdict_needs_a_band_or_a_threshold() -> None:
    with pytest.raises(ValueError, match="band"):
        reproduced(band=None)
    assert reproduced(band=None, threshold=D("0.001"))


def test_within_tolerance_needs_the_tolerance_that_decided_it() -> None:
    with pytest.raises(ValueError, match="tolerance"):
        reproduced(verdict=WITHIN_TOLERANCE)
    assert reproduced(verdict=WITHIN_TOLERANCE, tolerance_band=(D("0.82"), D("0.92")))
    assert reproduced(verdict=WITHIN_TOLERANCE, band=None, threshold=D("0.001"),
                      tolerance_threshold=D("0.0015"))


def test_an_unknown_verdict_is_refused() -> None:
    with pytest.raises(ValueError):
        reproduced(verdict="PROBABLY-FINE")


def test_unverified_needs_a_cause() -> None:
    with pytest.raises(ValueError, match="cause"):
        unverified(None)  # type: ignore[arg-type]


def test_only_unverified_carries_a_cause() -> None:
    with pytest.raises(ValueError, match="cause"):
        Verdict(verdict=REPRODUCED, cause=causes.NO_BINDING, **EVIDENCE)


@pytest.mark.parametrize("cause", ["MODEL_ONLY_SIGNAL", "PROPOSER_UNGROUNDED", "LOOKS_WRONG"])
def test_a_cause_outside_the_vocabulary_is_refused(cause: str) -> None:
    with pytest.raises(ValueError, match="vocabulary"):
        unverified(cause)


def test_an_unverified_without_evidence_is_fine_and_unbound() -> None:
    verdict = unverified(causes.WONT_RUN)
    assert not verdict.bound
    assert not verdict.review_required


def test_bound_means_a_value_was_located() -> None:
    assert unverified(causes.UNSUPPORTED_VALUE_KIND, located_text="0.85").bound


@pytest.mark.parametrize("field", ["rederived", "delta", "band"])
def test_a_float_anywhere_is_refused(field: str) -> None:
    value = (0.865, 0.875) if field == "band" else 0.8712
    with pytest.raises(TypeError):
        reproduced(**{field: value})


def test_the_record_is_frozen() -> None:
    with pytest.raises(AttributeError):
        reproduced().verdict = DIVERGED  # type: ignore[misc]
    assert replace(reproduced(), claim_id="c2").claim_id == "c2"


class TestVerdictSet:
    def test_coverage_is_derived_from_the_records(self) -> None:
        verdicts = (
            reproduced(claim_id="a"),
            reproduced(claim_id="b", verdict=DIVERGED),
            unverified(causes.NO_BINDING, claim_id="c"),
            unverified(causes.ARTIFACT_PRECISION_COARSER, claim_id="d", located_text="0.87"),
        )
        coverage = VerdictSet(run_id="r", verdicts=verdicts).coverage
        assert coverage == {
            "claims": 4,
            "bound": 3,
            "by_verdict": {REPRODUCED: 1, WITHIN_TOLERANCE: 0, DIVERGED: 1, UNVERIFIED: 2},
            "by_cause": {causes.ARTIFACT_PRECISION_COARSER: 1, causes.NO_BINDING: 1},
        }

    def test_verdicts_must_be_sorted_and_unique_by_claim_id(self) -> None:
        with pytest.raises(ValueError):
            VerdictSet(run_id="r", verdicts=(reproduced(claim_id="b"), reproduced(claim_id="a")))
        with pytest.raises(ValueError):
            VerdictSet(run_id="r", verdicts=(reproduced(), reproduced()))

    def test_an_empty_set_has_zero_coverage(self) -> None:
        coverage = VerdictSet(run_id=None, verdicts=()).coverage
        assert coverage["claims"] == 0 and coverage["bound"] == 0
        assert coverage["by_cause"] == {}
