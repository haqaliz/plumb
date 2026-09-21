"""Tests for the admission gate — the only door a `Claim` comes through.

Three things are under test here, and only the first is about behaviour.

**Grounding (M5).** A candidate becomes a `Claim` only if its span still yields its
text in this paper. The invariant the whole gate exists to hold is stated once, and
every admitted claim in this file is checked against it:

    normalized_text[claim.location.start:claim.location.end] == claim.reported_value.text

A claim whose location does not reproduce its own value is a claim a reader cannot
check, and C6 bundles that location for a third party to replay.

**Sole construction (D1).** `TestTheGateIsTheSoleConstructor` parses every module in
the package and asserts that `admit.py` is the only one that calls `Claim(...)`. That
is the guardrail the BYOK proposer will later need: if the deterministic core built
records directly, the proposer would arrive to find a second door already standing
open, and a model's proposal could reach a `Claim` without ever being re-grounded
(`ARCHITECTURE.md:59-61`, `CLAUDE.md` #4). The scan is self-tested in both directions,
for the reason `test_determinism.py` gives at length: a guard nobody has seen fire is
not a guard.

**Refusal is a record, never a silence (M4/D2).** Every path that does not produce a
`Claim` produces a `NonClaim` with a named cause. `admit` never returns `None`, and
that is asserted over a grid rather than at one call site. A silent drop is
indistinguishable from a claim that was never there, and it flatters the coverage
number the Phase 0 gate rests on.

The cause vocabulary is **extraction-side**. `TestTheCauseVocabularyIsExtractionSide`
pins that it borrows nothing from C4: this aspect runs nothing, so it may not emit
`REPRODUCED`, `WITHIN-TOLERANCE`, `DIVERGED` or `UNVERIFIED`, and a cause that looked
like one would be read downstream as a verdict this layer has no standing to assign.

This module emits no verdicts.
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from plumb.extract.admit import (
    CAUSE_PARTIAL_VALUE,
    CAUSE_STUDY_PARAMETER,
    CAUSE_UNGROUNDED,
    CAUSE_UNNAMED_METRIC,
    CAUSE_UNPARSED_VALUE,
    NON_CLAIM_CAUSES,
    NonClaim,
    admit,
)
from plumb.extract.candidates import (
    SECTION_RESULTS,
    Candidate,
    extract_candidates,
)
from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, Location, normalize_text
from plumb.extract.study import StudyParameter
from plumb.extract.value import Bound, ClaimValue, Point, PlusMinus, Range

_PACKAGE = Path(__file__).parents[2] / "src" / "plumb" / "extract"


#: A paper small enough to reason about and wide enough to carry one of every value
#: notation: a bare point, a reported N, a ± margin, a bound and an en-dash range.
PAPER = (
    "## Results\n"
    "\n"
    "The model reached AUC 0.87 on the held-out cohort (n = 412).\n"
    "Recall was 0.85 ± 0.03 and the effect held at p < 0.001.\n"
    "Dropout ran 12–15% across sites.\n"
)

SENTENCE = "The model reached AUC 0.87 on the held-out cohort (n = 412)."


def span_of(needle: str, *, occurrence: int = 0) -> CharSpan:
    """The span a correct extractor would emit for `needle` inside `PAPER`."""
    start = -1
    for _ in range(occurrence + 1):
        start = PAPER.index(needle, start + 1)
    return CharSpan(start, start + len(needle))


def candidate(
    text: str = "0.87",
    *,
    span: CharSpan | None = None,
    occurrence: int = 0,
    context: str = SENTENCE,
    section_hint: str = SECTION_RESULTS,
) -> Candidate:
    """A candidate that grounds in `PAPER`, with named parts replaced per test.

    `occurrence` is not convenience. `"12"` occurs twice in this paper — once as the
    range endpoint in `12–15%` and once *inside* `412` — and a helper that silently
    took the first would have quietly built a candidate whose span cuts a number in
    half. It did, and the gate admitted it as `Claim(12)` from a paper that says
    `412`; see `TestPartialValues.test_a_slice_of_a_longer_number_is_refused`.
    """
    return Candidate(
        text=text,
        span=span_of(text, occurrence=occurrence) if span is None else span,
        context=context,
        section_hint=section_hint,
    )


def admitted(**overrides: object) -> Claim | NonClaim:
    """`admit` with a full, plausible set of arguments, overridden per test."""
    arguments: dict[str, object] = {
        "candidate": candidate(),
        "normalized_text": PAPER,
        "metric": "AUC",
        "units": None,
        "artifact_hint": None,
        "tolerance_hint": None,
    }
    arguments.update(overrides)
    subject = arguments.pop("candidate")
    return admit(subject, **arguments)  # type: ignore[arg-type]


def assert_location_reproduces_the_value(claim: Claim, text: str = PAPER) -> None:
    """The invariant the gate exists to hold, applied to one claim."""
    assert isinstance(claim.location, CharSpan)
    quoted = text[claim.location.start : claim.location.end]
    assert quoted == claim.reported_value.text, (
        f"the claim's location quotes {quoted!r} but its reported value is "
        f"{claim.reported_value.text!r}; a claim whose location does not reproduce "
        "its own value cannot be checked by the reader C6 hands the bundle to."
    )


class TestThePaperFixtureIsAlreadyNormalized:
    """Vacuity control: every span below is measured against the normal form."""

    def test_the_fixture_is_its_own_normal_form(self) -> None:
        assert normalize_text(PAPER) == PAPER


class TestGrounding:
    """M5: a span that still yields its text is the whole of admission's evidence."""

    def test_a_grounded_candidate_becomes_a_claim(self) -> None:
        result = admitted()

        assert isinstance(result, Claim)
        assert result.metric == "AUC"
        assert isinstance(result.reported_value, Point)
        assert result.reported_value.text == "0.87"
        assert result.reported_value.value == Decimal("0.87")

    def test_the_admitted_claims_span_round_trips(self) -> None:
        result = admitted()

        assert isinstance(result, Claim)
        assert result.location == span_of("0.87")
        assert_location_reproduces_the_value(result)

    def test_every_supplied_field_reaches_the_record(self) -> None:
        result = admitted(
            units="%",
            artifact_hint="results/eval.py::auc",
            tolerance_hint="within 0.01",
        )

        assert isinstance(result, Claim)
        assert result.units == "%"
        assert result.artifact_hint == "results/eval.py::auc"
        assert result.tolerance_hint == "within 0.01"

    def test_a_span_that_no_longer_matches_is_not_grounded(self) -> None:
        """The candidate says `0.87`; that span holds something else in this paper."""
        moved = candidate("0.87", span=CharSpan(0, 4))

        result = admitted(candidate=moved)

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNGROUNDED
        assert result.text == "0.87"
        assert result.location == CharSpan(0, 4)

    def test_a_span_past_the_end_of_the_paper_is_not_grounded(self) -> None:
        """Python slicing clamps, so this is the case a naive equality check passes.

        `"abc"[0:1000] == "abc"` is `True`. A span that runs off the end therefore
        *appears* to round-trip while recording a location that covers a thousand
        characters of a paper that has three — and that location is what gets bundled
        and replayed against another copy of the paper.
        """
        end = len(PAPER)
        overrun = Candidate(
            text=PAPER[end - 4 : end],
            span=CharSpan(end - 4, end + 1000),
            context=SENTENCE,
            section_hint=SECTION_RESULTS,
        )

        result = admitted(candidate=overrun)

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNGROUNDED

    def test_a_zero_width_span_grounds_nothing(self) -> None:
        """`text[5:5] == ""` holds against every paper ever written."""
        empty = Candidate(
            text="",
            span=CharSpan(5, 5),
            context=SENTENCE,
            section_hint=SECTION_RESULTS,
        )

        result = admitted(candidate=empty)

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNGROUNDED

    def test_a_span_padded_with_whitespace_is_not_grounded(self) -> None:
        """A span must address the value tightly, or the invariant cannot hold.

        `parse_value` strips, so a padded candidate would produce a claim whose
        `reported_value.text` is `0.87` and whose location quotes ` 0.87`. The
        quotation and the value would differ by exactly the whitespace nobody looked
        at, which is the sort of near-miss that survives review.
        """
        start = PAPER.index("0.87") - 1
        padded = Candidate(
            text=PAPER[start : start + 5],
            span=CharSpan(start, start + 5),
            context=SENTENCE,
            section_hint=SECTION_RESULTS,
        )
        assert padded.text == " 0.87"

        result = admitted(candidate=padded)

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNGROUNDED

    def test_grounding_is_against_the_text_passed_not_the_text_extracted_from(
        self,
    ) -> None:
        """A candidate from one paper does not ground against another.

        The gate re-checks; it does not take the candidate's word for it. This is the
        case that matters when a proposer hands back a span it computed against a
        different revision of the paper.
        """
        other = "Recall was 0.85 ± 0.03 and the effect held at p < 0.001.\n"

        result = admitted(normalized_text=other)

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNGROUNDED


class TestTheNormalizedTextContract:
    """The parameter is named `normalized_text`, and the gate takes it at its word."""

    def test_raw_text_with_crlf_does_not_silently_ground(self) -> None:
        """Deliberate: the gate does not re-normalize, and here is the consequence.

        `normalize_text` is idempotent, so calling it here would be harmless per call
        and quadratic per paper — O(len(paper)) work for each of the paper's numbers.
        The candidates module hit exactly that shape and it cost twenty-two seconds on
        a four-thousand-line paper. So the caller normalizes once, at intake, and a
        caller who does not gets a named refusal rather than a wrong offset.
        """
        crlf = PAPER.replace("\n", "\r\n")
        assert normalize_text(crlf) == PAPER

        result = admitted(normalized_text=crlf)

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNGROUNDED

    def test_the_same_candidate_grounds_against_the_normalized_twin(self) -> None:
        # The other half: normalization at intake is all it takes to ground.
        crlf = PAPER.replace("\n", "\r\n")

        result = admitted(normalized_text=normalize_text(crlf))

        assert isinstance(result, Claim)
        assert_location_reproduces_the_value(result)


class TestTheCauseVocabulary:
    """Closed, named, and each cause reachable by a real call."""

    def test_the_vocabulary_is_exactly_the_five_named_causes(self) -> None:
        assert NON_CLAIM_CAUSES == frozenset(
            {
                CAUSE_UNGROUNDED,
                CAUSE_PARTIAL_VALUE,
                CAUSE_STUDY_PARAMETER,
                CAUSE_UNNAMED_METRIC,
                CAUSE_UNPARSED_VALUE,
            }
        )

    def test_an_unknown_cause_is_refused_at_construction(self) -> None:
        """Closed means closed: an invented cause would reach the corpus as a fact."""
        with pytest.raises(ValueError):
            NonClaim(cause="looks_wrong", text="0.87", location=span_of("0.87"))

    def test_ungrounded_is_reachable(self) -> None:
        result = admitted(candidate=candidate("0.87", span=CharSpan(0, 4)))

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNGROUNDED

    def test_partial_value_is_reachable(self) -> None:
        """`0.001` in `p < 0.001` is a threshold, not a reported point value.

        Admitting it as `Point(0.001)` would restate the paper's claim as `p = 0.001`,
        which the paper never made, and a re-derived `0.0009` would then look like a
        contradiction. `value.py`'s docstring names this as the reason `Bound` exists;
        the gate refuses rather than creating it.
        """
        result = admitted(candidate=candidate("0.001"), metric="p-value")

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_PARTIAL_VALUE

    def test_study_parameter_is_reachable(self) -> None:
        result = admitted(candidate=candidate("412"), metric="sample size")

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_STUDY_PARAMETER

    def test_unnamed_metric_is_reachable(self) -> None:
        result = admitted(metric="")

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNNAMED_METRIC

    @pytest.mark.parametrize("blank", ["", " ", "\t", "\n  "])
    def test_a_whitespace_metric_is_data_not_a_crash(self, blank: str) -> None:
        """`Claim` raises on an empty metric; the gate must not propagate that.

        A proposer that names no quantity is a fact about the proposal, recorded. An
        exception here would lose the rest of the paper to one bad proposal — the same
        argument `parse_value` makes for returning `None` rather than raising.
        """
        result = admitted(metric=blank)

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNNAMED_METRIC

    def test_unparsed_value_is_reachable(self) -> None:
        """A grounded span whose text is not a number the value layer can read."""
        word = candidate("Results", span=span_of("Results"))

        result = admitted(candidate=word, metric="AUC")

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNPARSED_VALUE

    def test_every_cause_in_the_vocabulary_is_reachable(self) -> None:
        """No cause may be declared and unreachable.

        A cause nothing emits is a line a future refusal can hide behind: the
        vocabulary would look complete while the case it names had quietly stopped
        being detected.
        """
        reached = {
            admitted(candidate=candidate("0.87", span=CharSpan(0, 4))),
            admitted(candidate=candidate("0.001"), metric="p-value"),
            admitted(candidate=candidate("412"), metric="sample size"),
            admitted(metric=""),
            admitted(candidate=candidate("Results", span=span_of("Results"))),
        }
        causes = {
            refusal.cause for refusal in reached if isinstance(refusal, NonClaim)
        }

        assert causes == NON_CLAIM_CAUSES


class TestTheCauseVocabularyIsExtractionSide:
    """C4's vocabulary is not this aspect's to borrow.

    This layer runs nothing. A cause that read as `UNVERIFIED` would arrive downstream
    looking like a verdict about whether the claim holds, when it is a fact about
    whether a number could be read out of a paper — and `UNVERIFIED` in particular is
    the verdict C4 assigns after an artifact *failed to decide*, which is a different
    statement about a different thing.
    """

    VERDICTS = frozenset(
        {"REPRODUCED", "WITHIN-TOLERANCE", "WITHIN_TOLERANCE", "DIVERGED", "UNVERIFIED"}
    )

    def test_no_cause_is_a_verdict(self) -> None:
        folded = {cause.upper() for cause in NON_CLAIM_CAUSES}

        assert not (folded & self.VERDICTS)

    def test_no_string_in_the_module_is_a_verdict(self) -> None:
        """Every string constant, not a text scan.

        The module's own prose names the verdicts in the passage explaining why it may
        not emit them — the same trap `test_determinism.py` documents, where a `grep`
        fires on the file that documents the rule. Equality on parsed string constants
        sees the constant and not the sentence about it.
        """
        tree = ast.parse((_PACKAGE / "admit.py").read_text(encoding="utf-8"))
        constants = {
            node.value.upper()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

        assert not (constants & self.VERDICTS)


class TestTheGateIsTheSoleConstructor:
    """D1: one door, and a test that fails when a second one opens.

    The BYOK proposer is out of scope, but the seam is built now. A `Claim(...)` call
    anywhere else in the package is that second door — the proposer would plug into a
    core that already constructs records directly, and its proposal would reach a
    `Claim` without being re-grounded against the paper.
    """

    SYNTHETIC_BYPASS = '''\
from plumb.extract.claim import Claim


def propose(value, span):
    return Claim(
        reported_value=value,
        units=None,
        metric="AUC",
        location=span,
        artifact_hint=None,
        tolerance_hint=None,
    )
'''

    SYNTHETIC_INNOCENT = '''\
"""A module that merely reads claims — including the word Claim in its prose."""


def metrics(claims):
    return sorted(claim.metric for claim in claims)
'''

    @staticmethod
    def constructs_claim(source: str) -> bool:
        tree = ast.parse(source)
        return any(
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id == "Claim")
                or (isinstance(node.func, ast.Attribute) and node.func.attr == "Claim")
            )
            for node in ast.walk(tree)
        )

    def test_the_scan_fires_on_a_second_door(self) -> None:
        assert self.constructs_claim(self.SYNTHETIC_BYPASS)

    def test_the_scan_stays_silent_on_a_module_that_only_reads_claims(self) -> None:
        assert not self.constructs_claim(self.SYNTHETIC_INNOCENT)

    def test_only_the_admission_gate_constructs_a_claim(self) -> None:
        constructors = sorted(
            path.name
            for path in sorted(_PACKAGE.rglob("*.py"))
            if self.constructs_claim(path.read_text(encoding="utf-8"))
        )

        assert constructors == ["admit.py"], (
            f"{constructors} construct a Claim. Admission through deterministic "
            "grounding is the only door a Claim may come through (plan D1, "
            "ARCHITECTURE.md:59-61): a second constructor is the path the BYOK "
            "proposer would later reach a Claim by without being re-grounded."
        )

    def test_the_scan_actually_covers_the_package(self) -> None:
        # Vacuity control: a scan that found no modules would agree with any answer.
        names = {path.name for path in _PACKAGE.rglob("*.py")}
        assert {"admit.py", "claim.py", "candidates.py", "dedup.py"} <= names


class TestNonClaimIsNotAClaim:
    """M4's separation, in both directions and by field names as well as by type.

    The same argument `StudyParameter` makes: a shared base is how the distinction
    erodes, because a later stage types against the base and starts accepting a
    refusal wherever it meant a claim. A `NonClaim` that reached a verdict stage as a
    claim would be a claim nobody could re-derive, counted in the denominator the
    Phase 0 gate rests on.
    """

    def test_a_non_claim_is_not_a_claim(self) -> None:
        refusal = admitted(metric="")

        assert isinstance(refusal, NonClaim)
        assert not isinstance(refusal, Claim)

    def test_a_claim_is_not_a_non_claim(self) -> None:
        result = admitted()

        assert isinstance(result, Claim)
        assert not isinstance(result, NonClaim)

    def test_the_two_types_share_no_base_class(self) -> None:
        assert set(NonClaim.__mro__) & set(Claim.__mro__) == {object}

    def test_a_non_claim_shares_no_base_with_a_study_parameter_either(self) -> None:
        assert set(NonClaim.__mro__) & set(StudyParameter.__mro__) == {object}

    def test_a_non_claim_is_rejected_where_a_claim_value_is_required(self) -> None:
        refusal = admitted(metric="")

        with pytest.raises(TypeError):
            Claim(
                reported_value=refusal,  # type: ignore[arg-type]
                units=None,
                metric="AUC",
                location=span_of("0.87"),
                artifact_hint=None,
                tolerance_hint=None,
            )

    def test_a_claim_is_rejected_where_a_candidate_is_required(self) -> None:
        result = admitted()

        with pytest.raises(TypeError):
            admitted(candidate=result)

    def test_a_non_claim_is_rejected_where_a_candidate_is_required(self) -> None:
        refusal = admitted(metric="")

        with pytest.raises(TypeError):
            admitted(candidate=refusal)

    @pytest.mark.parametrize(
        "attribute",
        ["reported_value", "metric", "units", "artifact_hint", "tolerance_hint", "id"],
    )
    def test_a_non_claim_does_not_duck_type_as_a_claim(self, attribute: str) -> None:
        """Separation by field name too: plenty of code reaches for `claim.metric`."""
        assert not hasattr(admitted(metric=""), attribute)

    @pytest.mark.parametrize("attribute", ["cause"])
    def test_a_claim_does_not_duck_type_as_a_non_claim(self, attribute: str) -> None:
        assert not hasattr(admitted(), attribute)

    def test_a_non_claim_is_not_a_value_or_a_location(self) -> None:
        refusal = admitted(metric="")

        assert not isinstance(refusal, ClaimValue)
        assert not isinstance(refusal, Location)


class TestTheNonClaimRecord:
    """Shape, and two deliberate absences."""

    def test_it_carries_the_refused_text_and_where_it_was(self) -> None:
        refusal = admitted(metric="")

        assert isinstance(refusal, NonClaim)
        assert refusal.text == "0.87"
        assert refusal.location == span_of("0.87")

    @pytest.mark.parametrize("missing", ["cause", "text", "location"])
    def test_every_field_must_be_stated(self, missing: str) -> None:
        fields: dict[str, object] = {
            "cause": CAUSE_UNGROUNDED,
            "text": "0.87",
            "location": span_of("0.87"),
        }
        del fields[missing]

        with pytest.raises(TypeError):
            NonClaim(**fields)  # type: ignore[arg-type]

    def test_it_is_frozen(self) -> None:
        refusal = NonClaim(
            cause=CAUSE_UNGROUNDED, text="0.87", location=span_of("0.87")
        )

        with pytest.raises(FrozenInstanceError):
            refusal.cause = CAUSE_UNPARSED_VALUE  # type: ignore[misc]

    @pytest.mark.parametrize("attribute", ["confidence", "id", "verdict"])
    def test_the_record_carries_no_confidence_no_id_and_no_verdict(
        self, attribute: str
    ) -> None:
        """Three absences, each a guardrail.

        `confidence` is a model's opinion, which `CLAUDE.md` #1 keeps off every record
        in this layer. `id` is absent because no merge requirement has been stated for
        refusals, and deriving one here would make it look as though the question had
        been settled. `verdict` is absent because this aspect runs nothing.
        """
        refusal = admitted(metric="")

        assert not hasattr(refusal, attribute)

    def test_it_cannot_be_given_an_attribute_after_construction(self) -> None:
        # `slots=True`, so the guardrail above cannot be re-opened by assignment.
        refusal = admitted(metric="")

        with pytest.raises((AttributeError, FrozenInstanceError)):
            object.__setattr__(refusal, "confidence", "0.9")

    def test_the_location_must_be_a_location(self) -> None:
        with pytest.raises(TypeError):
            NonClaim(cause=CAUSE_UNGROUNDED, text="0.87", location=(22, 26))  # type: ignore[arg-type]

    def test_the_text_must_be_a_string(self) -> None:
        with pytest.raises(TypeError):
            NonClaim(cause=CAUSE_UNGROUNDED, text=None, location=span_of("0.87"))  # type: ignore[arg-type]


class TestAdmitNeverReturnsNone:
    """M4: never silent. Asserted over a grid, not at one call site."""

    CANDIDATES = (
        candidate("0.87"),
        candidate("412"),
        candidate("0.001"),
        candidate("0.03"),
        candidate("12"),
        candidate("15"),
        candidate("Results", span=span_of("Results")),
        candidate("0.87", span=CharSpan(0, 4)),
        Candidate(
            text="", span=CharSpan(0, 0), context="", section_hint=SECTION_RESULTS
        ),
    )

    @pytest.mark.parametrize("subject", CANDIDATES)
    @pytest.mark.parametrize("metric", ["AUC", "", "  ", "p-value"])
    @pytest.mark.parametrize("units", [None, "", "%"])
    def test_every_combination_yields_a_record(
        self, subject: Candidate, metric: str, units: str | None
    ) -> None:
        result = admit(
            subject,
            normalized_text=PAPER,
            metric=metric,
            units=units,
            artifact_hint=None,
            tolerance_hint=None,
        )

        assert result is not None
        assert isinstance(result, (Claim, NonClaim))

    def test_every_candidate_in_a_whole_paper_yields_a_record(self) -> None:
        results = [
            admit(subject, normalized_text=PAPER, metric="AUC")
            for subject in extract_candidates(PAPER)
        ]

        assert results, "the fixture yielded no candidates; the test is vacuous"
        assert all(isinstance(r, (Claim, NonClaim)) for r in results)

    def test_a_refusal_is_never_returned_as_an_absence(self) -> None:
        # The shape the plan forbids: `None` for "not a claim" is indistinguishable
        # from "nothing was there", and the coverage number cannot tell them apart.
        refusals = [
            admitted(metric=""),
            admitted(candidate=candidate("0.87", span=CharSpan(0, 4))),
            admitted(candidate=candidate("412")),
        ]

        assert all(isinstance(r, NonClaim) and r.cause in NON_CLAIM_CAUSES
                   for r in refusals)


class TestCausePrecedence:
    """Which refusal wins when several apply. ORDER IS THE CONTRACT.

    Each check presupposes the one before it: there is no point reporting that a value
    would not parse if the span does not address that text in the first place, and a
    cause that varied with the order of the checks would make the discrepancy corpus
    record the implementation rather than the paper.
    """

    def test_ungrounded_beats_every_other_cause(self) -> None:
        # Ungrounded, unparseable, no metric, and adjacent to an operator at once.
        result = admit(
            candidate("0.001", span=CharSpan(0, 5)),
            normalized_text=PAPER,
            metric="",
        )

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNGROUNDED

    def test_partial_value_beats_the_missing_metric(self) -> None:
        result = admitted(candidate=candidate("0.001"), metric="")

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_PARTIAL_VALUE

    def test_study_parameter_beats_the_missing_metric(self) -> None:
        """A reported N is study metadata whatever metric a caller attaches to it.

        This is the guardrail direction: a future proposer that confidently labelled
        `412` as `"cohort AUC"` still does not get a claim out of it.
        """
        result = admitted(candidate=candidate("412"), metric="")

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_STUDY_PARAMETER

    def test_the_missing_metric_beats_the_unparseable_value(self) -> None:
        word = candidate("Results", span=span_of("Results"))

        result = admitted(candidate=word, metric="")

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_UNNAMED_METRIC


class TestPartialValues:
    """A span that covers part of a value, and the caller's remedy.

    The candidate layer emits bare numbers on purpose — `Candidate.text` carries no
    `%`, no unit and no operator. For `0.87` that is the whole value. For `p < 0.001`,
    `0.85 ± 0.03` and `12–15%` it is a fragment, and admitting the fragment as a
    `Point` would put a number in the record that the paper never asserted on its own.

    The remedy is the caller's: widen the candidate to cover the notation as written.
    `Candidate` does not require its text to be a bare number, so the seam already
    exists, and a widened candidate grounds and parses into the right variant. That
    widening is the selection rule's job (M3, part 2) and is not done here.
    """

    @pytest.mark.parametrize(
        ("text", "occurrence", "why"),
        [
            ("0.001", 0, "the magnitude of `p < 0.001`"),
            ("0.03", 0, "the margin of `0.85 ± 0.03`"),
            ("0.85", 0, "the centre of `0.85 ± 0.03`"),
            ("12", 1, "the low endpoint of `12–15%`"),
            ("15", 0, "the high endpoint of `12–15%`"),
        ],
    )
    def test_a_fragment_of_a_wider_value_is_refused(
        self, text: str, occurrence: int, why: str
    ) -> None:
        subject = candidate(text, occurrence=occurrence)

        result = admitted(candidate=subject, metric="metric")

        assert isinstance(result, NonClaim), why
        assert result.cause == CAUSE_PARTIAL_VALUE, why

    @pytest.mark.parametrize(
        ("text", "inside"), [("12", "412"), ("87", "0.87"), ("0.8", "0.87")]
    )
    def test_a_slice_of_a_longer_number_is_refused(
        self, text: str, inside: str
    ) -> None:
        """The fragment that passes the obvious grounding check, and the worst one.

        `"412"[1:3] == "12"`, so the span round-trips perfectly — and the claim reads
        `12` out of a paper whose number is `412`. `extract_candidates` never produces
        such a span (a number may not start inside a run of digits), which is exactly
        why the gate must: the spans that reach this function from a BYOK proposer are
        the ones the deterministic tokenizer did not draw.
        """
        start = PAPER.index(inside) + inside.index(text)
        sliced = Candidate(
            text=text,
            span=CharSpan(start, start + len(text)),
            context=SENTENCE,
            section_hint=SECTION_RESULTS,
        )
        assert PAPER[sliced.span.start : sliced.span.end] == text

        result = admitted(candidate=sliced, metric="metric")

        assert isinstance(result, NonClaim)
        assert result.cause == CAUSE_PARTIAL_VALUE

    def test_a_number_at_the_very_start_of_the_paper_is_not_a_fragment(self) -> None:
        # Boundary control for the look-behind: there is nothing before offset 0, and
        # a window that read past the start would either raise or wrap around.
        text = "412 patients were enrolled.\n"
        subject = Candidate(
            text="412",
            span=CharSpan(0, 3),
            context=text,
            section_hint=SECTION_RESULTS,
        )

        result = admit(subject, normalized_text=text, metric="cohort size")

        assert isinstance(result, Claim)

    def test_a_standalone_number_is_not_a_fragment(self) -> None:
        # The control: the detector must not refuse the ordinary case.
        result = admitted()

        assert isinstance(result, Claim)

    @pytest.mark.parametrize(
        ("text", "variant"),
        [
            ("p < 0.001", Bound),
            ("0.85 ± 0.03", PlusMinus),
            ("12–15%", Range),
        ],
    )
    def test_a_widened_candidate_admits_as_the_right_variant(
        self, text: str, variant: type
    ) -> None:
        widened = candidate(text)

        result = admitted(candidate=widened, metric="metric")

        assert isinstance(result, Claim)
        assert isinstance(result.reported_value, variant)
        assert_location_reproduces_the_value(result)

    def test_the_bound_keeps_its_operator_rather_than_becoming_a_point(self) -> None:
        # The specific invention this refusal exists to prevent: `p = 0.001`.
        result = admitted(candidate=candidate("p < 0.001"), metric="p-value")

        assert isinstance(result, Claim)
        assert isinstance(result.reported_value, Bound)
        assert result.reported_value.op == "<"
        assert result.reported_value.magnitude == Decimal("0.001")


class TestTheGateIsNotTheSelectionRule:
    """The boundary, pinned so nobody reads this suite as evidence of selection.

    A publication year, a figure number and an axis label all come through this gate
    as claims today, and that is correct: deciding *which* numbers are worth admitting
    is M3, deferred to part 2 so the rule can be scored against labels it did not
    author (plan §0). The gate checks that a proposed claim is really there; it does
    not decide whether it is worth proposing.

    Written as positive assertions rather than left unsaid, because the failure mode is
    a reader concluding from a green suite that years are already rejected — and then
    part 2 landing a rejection list nobody scores.
    """

    @pytest.mark.parametrize(
        ("document", "text", "what"),
        [
            ("Published in 2026 by the group.\n", "2026", "a publication year"),
            ("See Figure 3 for the curve.\n", "3", "a figure number"),
            ("The x-axis runs to 100 units.\n", "100", "an axis label"),
        ],
    )
    def test_the_gate_admits_numbers_selection_will_later_reject(
        self, document: str, text: str, what: str
    ) -> None:
        start = document.index(text)
        subject = Candidate(
            text=text,
            span=CharSpan(start, start + len(text)),
            context=document,
            section_hint=SECTION_RESULTS,
        )

        result = admit(subject, normalized_text=document, metric="metric")

        assert isinstance(result, Claim), (
            f"{what} was refused by the admission gate. Rejecting it is M3's job and "
            "is deferred to part 2 on purpose: a rule written here could not be "
            "scored against labels it did not author."
        )


class TestKnownLimitsOfTheFragmentCheck:
    """What the fragment check misses and what it catches imprecisely.

    Recorded as tests so the limits are visible in the suite rather than discovered by
    the first person to read a corpus. Neither direction invents a claim: the miss
    admits a point where a wider value existed, and the imprecise catch refuses a
    number that selection would have rejected anyway.
    """

    def test_an_interval_endpoint_is_not_yet_recognised_as_a_fragment(self) -> None:
        """`95% CI [0.81, 0.89]` needs bracket structure, not one adjacent character.

        The `0.81` therefore admits as `Point(0.81)` today. It is a real gap: the
        paper reported an interval, and a point read out of it is not what it said.
        Closing it belongs with the widening the selection rule will do in part 2,
        where the bracket structure is already being read.
        """
        document = "The 95% CI [0.81, 0.89] held across sites.\n"
        start = document.index("0.81")
        subject = Candidate(
            text="0.81",
            span=CharSpan(start, start + 4),
            context=document,
            section_hint=SECTION_RESULTS,
        )

        result = admit(subject, normalized_text=document, metric="AUC")

        assert isinstance(result, Claim)
        assert isinstance(result.reported_value, Point)

    def test_a_comma_separated_citation_list_is_refused_as_a_fragment(self) -> None:
        """`[1,2]` gives `partial_value`, and the cause is the honest one.

        A comma directly between two digits is a thousands separator or a
        citation list, and the gate cannot tell which from the characters alone.
        `partial_value` says exactly that: this span sits inside something longer that
        could be a number, so it will not become a claim on its own. Selection will
        keep reference numerals from reaching the gate at all (M3); until it does, a
        refusal is the conservative direction.
        """
        document = "Prior work [1,2] reported the same effect.\n"

        results = [
            admit(subject, normalized_text=document, metric="AUC")
            for subject in extract_candidates(document)
        ]

        assert [r.text for r in results if isinstance(r, NonClaim)] == ["1", "2"]
        assert all(
            isinstance(r, NonClaim) and r.cause == CAUSE_PARTIAL_VALUE for r in results
        )


class TestArgumentTypes:
    """A wrong type is a programming error; bad data is a `NonClaim`.

    The two must not be confused in either direction. A `TypeError` recorded as a
    refusal would put our own bug into the discrepancy corpus as though it were a fact
    about the paper; a refusal raised as an exception would lose the rest of the paper.
    """

    def test_the_candidate_must_be_a_candidate(self) -> None:
        with pytest.raises(TypeError):
            admitted(candidate="0.87")

    def test_the_normalized_text_must_be_a_string(self) -> None:
        with pytest.raises(TypeError):
            admitted(normalized_text=None)

    def test_the_metric_must_be_a_string(self) -> None:
        # `None` is not "no metric stated"; it is a caller who passed the wrong thing.
        with pytest.raises(TypeError):
            admitted(metric=None)

    @pytest.mark.parametrize(
        "field", ["units", "artifact_hint", "tolerance_hint"]
    )
    def test_the_optional_fields_must_be_strings_or_none(self, field: str) -> None:
        with pytest.raises(TypeError):
            admitted(**{field: 0.87})

    def test_the_optional_fields_default_to_none(self) -> None:
        """The three hints default; the metric does not.

        `Claim` requires every field to be stated because `None` is a fact the caller
        asserts. That rule is right for the record and wrong for the gate: `admit` has
        one mandatory job, and the defaults here say "nobody looked", which is what
        the deterministic core can honestly say about an artifact hint it has no way
        to compute yet.
        """
        result = admit(candidate(), normalized_text=PAPER, metric="AUC")

        assert isinstance(result, Claim)
        assert result.units is None
        assert result.artifact_hint is None
        assert result.tolerance_hint is None


class TestDeterminism:
    """Same inputs, same records — including the derived id."""

    def test_admitting_twice_gives_equal_records(self) -> None:
        first, second = admitted(), admitted()

        assert first == second
        assert isinstance(first, Claim) and isinstance(second, Claim)
        assert first.id == second.id

    def test_refusing_twice_gives_equal_records(self) -> None:
        assert admitted(metric="") == admitted(metric="")

    def test_the_id_is_the_records_own_derivation(self) -> None:
        # The gate does not invent an identity scheme of its own: the id a claim gets
        # here is the one `Claim` derives from (value text, metric, units), so a claim
        # admitted from a paper and the same claim rebuilt elsewhere share it.
        result = admitted(units="%")
        direct = Claim(
            reported_value=Point(text="0.87", value=Decimal("0.87")),
            units="%",
            metric="AUC",
            location=span_of("0.87"),
            artifact_hint=None,
            tolerance_hint=None,
        )

        assert isinstance(result, Claim)
        assert result.id == direct.id


class TestTheGateHoldsOverAWholePaper:
    """The invariant, applied to every claim the fixture paper produces."""

    def test_every_admitted_claim_quotes_its_own_value(self) -> None:
        admitted_claims = [
            result
            for subject in extract_candidates(PAPER)
            if isinstance(
                result := admit(subject, normalized_text=PAPER, metric="metric"), Claim
            )
        ]

        assert admitted_claims, "nothing was admitted; the test is vacuous"
        for claim in admitted_claims:
            assert_location_reproduces_the_value(claim)

    def test_every_refusal_names_a_cause_from_the_vocabulary(self) -> None:
        refusals = [
            result
            for subject in extract_candidates(PAPER)
            if isinstance(
                result := admit(subject, normalized_text=PAPER, metric="metric"),
                NonClaim,
            )
        ]

        assert refusals, "nothing was refused; the test is vacuous"
        for refusal in refusals:
            assert refusal.cause in NON_CLAIM_CAUSES

    def test_every_candidate_is_accounted_for_exactly_once(self) -> None:
        # Coverage arithmetic: claims + refusals = candidates, with nothing lost in
        # between. This is the sum the Phase 0 gate's denominator is drawn from.
        candidates = extract_candidates(PAPER)
        results = [
            admit(subject, normalized_text=PAPER, metric="metric")
            for subject in candidates
        ]

        claims = [r for r in results if isinstance(r, Claim)]
        refusals = [r for r in results if isinstance(r, NonClaim)]

        assert len(claims) + len(refusals) == len(candidates)
