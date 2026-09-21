"""Tests for M11: populating `StudyParameter` from a paper's reported sample sizes.

`test_study.py` built the record and asserted it is not a `Claim`. This file is the
other half — actually reading N out of a paper — and its load-bearing test is
`TestNIsNotInTheClaimOutput`.

**Why that test and not the happy path.** Reported N has to be extracted, because C7
verifies a paper's reported statistics against it. But no execution ever re-derives a
sample size. The Phase 0 gate is a coverage number — the fraction of headline claims
that bind to an artifact and re-derive — so admitting N as a claim would drop a
permanently-unbindable item into that denominator, and the number would come out lower
for a reason that has nothing to do with how well Plumb works. Extracting N and keeping
it out of the claim output are one requirement, not two, and a test that only checked
the first would pass while the gate number quietly drifted.

**One recogniser, two callers.** `study_parameters` emits the parameters and `admit`
refuses the same numbers with `study_parameter`. `TestTheTwoCallersAgree` asserts the
correspondence over a whole document rather than leaving two call sites to stay in step
by discipline — a number that fell between them would be extracted as neither, which is
the silent drop `NonClaim` exists to prevent.

This module emits no verdicts.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from plumb.extract.admit import (
    CAUSE_STUDY_PARAMETER,
    NonClaim,
    admit,
    study_parameters,
)
from plumb.extract.candidates import extract_candidates
from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.study import StudyParameter
from plumb.extract.value import Point, parse_value

#: The four spellings the plan names, plus the ones a paper adds for free: italicised
#: `n` in both Markdown emphasis styles, bold, and whitespace nobody is consistent
#: about. Statistical *n* is conventionally italicised, so the emphasised forms are the
#: common case in a converted paper rather than an exotic one.
RECOGNISED = (
    "We enrolled a cohort (n = 412) from three sites.\n",
    "We enrolled a cohort of N=412 patients.\n",
    "We enrolled n=412 patients.\n",
    "The cohort was n = 412 in total.\n",
    "The cohort was *n* = 412 in total.\n",
    "The cohort was _n_ = 412 in total.\n",
    "The cohort was __n__ = 412 in total.\n",
    "The cohort was (_n_ = 412) in total.\n",
    "The cohort was n  =  412 in total.\n",
)

PAPER = (
    "## Results\n"
    "\n"
    "The model reached AUC 0.87 on the held-out cohort (n = 412).\n"
    "A second site contributed N=1,024 more participants.\n"
)


def only(parameters: tuple[StudyParameter, ...]) -> StudyParameter:
    """The single parameter, or a failure that says how many there really were."""
    assert len(parameters) == 1, f"expected exactly one parameter, got {parameters}"
    return parameters[0]


def claims_of(document: str, *, metric: str = "AUC") -> list[Claim]:
    """Every claim the gate admits from `document`, with a plausible metric attached.

    A plausible metric on purpose. Passing `""` would make every candidate a refusal
    for the wrong reason, and the test below would pass without the sample-size rule
    existing at all.
    """
    text = normalize_text(document)
    return [
        result
        for candidate in extract_candidates(text)
        if isinstance(
            result := admit(candidate, normalized_text=text, metric=metric), Claim
        )
    ]


class TestRecognisedForms:
    """The spellings a paper actually uses, one test each."""

    @pytest.mark.parametrize("document", RECOGNISED)
    def test_a_reported_sample_size_is_extracted(self, document: str) -> None:
        parameter = only(study_parameters(document))

        assert parameter.value.text == "412"
        assert isinstance(parameter.value, Point)
        assert parameter.value.value == Decimal("412")

    @pytest.mark.parametrize("document", RECOGNISED)
    def test_the_location_quotes_the_reported_number(self, document: str) -> None:
        """The same invariant the admission gate holds for claims.

        A parameter whose location does not reproduce its own value is a parameter C7
        cannot show the reader it checked a statistic against.
        """
        text = normalize_text(document)
        parameter = only(study_parameters(document))

        assert isinstance(parameter.location, CharSpan)
        quoted = text[parameter.location.start : parameter.location.end]
        assert quoted == parameter.value.text

    @pytest.mark.parametrize(
        ("document", "name"),
        [
            ("A cohort of n = 412 patients.\n", "n"),
            ("A cohort of N = 412 patients.\n", "N"),
            ("A cohort of *n* = 412 patients.\n", "n"),
            ("A cohort of _n_ = 412 patients.\n", "n"),
            ("A cohort of __N__ = 412 patients.\n", "N"),
        ],
    )
    def test_the_name_is_recorded_as_the_paper_wrote_it(
        self, document: str, name: str
    ) -> None:
        """`StudyParameter.name` is documented as the parameter *as the paper named
        it*. Case-folding here would record this module's rendering rather than the
        paper's; C7 can fold case when it looks one up, and cannot un-fold it.

        The emphasised rows pin that the name is the *letter*, not the markup around
        it. The recogniser captures the delimiter in group 1 and the name in group 2,
        and `StudyParameter.name` accepts any non-empty string — so reading the wrong
        group would record a parameter named `"_"` and nothing would complain.
        """
        assert only(study_parameters(document)).name == name

    def test_the_value_keeps_the_papers_thousands_separator(self) -> None:
        parameter = only(study_parameters("We enrolled N=1,024 participants.\n"))

        assert parameter.value.text == "1,024"
        assert isinstance(parameter.value, Point)
        assert parameter.value.value == Decimal("1024")

    def test_several_reported_sizes_all_come_out(self) -> None:
        parameters = study_parameters(PAPER)

        assert [p.value.text for p in parameters] == ["412", "1,024"]
        assert [p.name for p in parameters] == ["n", "N"]


class TestNotRecognised:
    """The other direction, which is where a recogniser does its damage.

    Every false positive here removes a number from the claim output — and therefore
    from the coverage denominator — so an over-eager rule flatters the Phase 0 gate in
    exactly the way a silent drop would.
    """

    @pytest.mark.parametrize(
        ("document", "why"),
        [
            ("The median = 412 across sites.\n", "`n` must not be part of a word"),
            ("The nn = 412 count was noted.\n", "the same, doubled"),
            ("The mean_n = 412 was noted.\n", "an underscore is word-like too"),
            (
                "The mean_n_ = 412 was noted.\n",
                "emphasis markers are only emphasis when something non-word opens "
                "them; here the `_n_` is the tail of an identifier",
            ),
            (
                "The p_n_ = 412 threshold applied.\n",
                "the same, with a one-letter stem — a subscripted variable, not a "
                "reported cohort",
            ),
            (
                "The _n_count = 412 field was set.\n",
                "an opening underscore that is not closed before the `=`",
            ),
            ("We enrolled 412 patients.\n", "no `n =` at all"),
            ("The cohort had n > 412 members.\n", "an inequality is not an equality"),
            ("Each of n\n= 412 sites reported.\n", "`n =` may not cross a line break"),
        ],
    )
    def test_a_number_that_is_not_a_reported_size_is_not_extracted(
        self, document: str, why: str
    ) -> None:
        assert study_parameters(document) == (), why

    def test_a_document_with_no_numbers_yields_nothing(self) -> None:
        assert study_parameters("No numbers appear in this sentence.\n") == ()

    def test_an_empty_document_yields_nothing(self) -> None:
        assert study_parameters("") == ()

    @pytest.mark.parametrize(
        "document",
        [
            "The median = 412 across sites.\n",
            "The nn = 412 count was noted.\n",
            "We enrolled 412 patients.\n",
            "The cohort was _n_ = 412 in total.\n",
        ],
    )
    def test_the_negative_cases_do_contain_numbers(self, document: str) -> None:
        # Vacuity control: the refusals above must be refusals, not documents the
        # candidate extractor found nothing in.
        assert extract_candidates(document)


class TestEmitsStudyParameterNeverAClaim:
    """M11's separation, asserted on records this module actually produced."""

    def test_the_record_is_a_study_parameter(self) -> None:
        assert isinstance(only(study_parameters(PAPER[:70])), StudyParameter)

    def test_the_record_is_not_a_claim(self) -> None:
        for parameter in study_parameters(PAPER):
            assert not isinstance(parameter, Claim)

    def test_the_record_is_not_a_non_claim_either(self) -> None:
        # A reported N is not a refusal: it is a thing successfully extracted, into
        # the type that exists for it. Recording it as a `NonClaim` would lose it.
        for parameter in study_parameters(PAPER):
            assert not isinstance(parameter, NonClaim)

    @pytest.mark.parametrize(
        "attribute",
        ["reported_value", "metric", "units", "artifact_hint", "tolerance_hint", "id"],
    )
    def test_it_does_not_duck_type_as_a_claim(self, attribute: str) -> None:
        assert not hasattr(only(study_parameters(PAPER[:70])), attribute)

    @pytest.mark.parametrize("attribute", ["confidence", "verdict"])
    def test_it_carries_no_confidence_and_no_verdict(self, attribute: str) -> None:
        assert not hasattr(only(study_parameters(PAPER[:70])), attribute)


class TestNIsNotInTheClaimOutput:
    """The test M11 exists for: N never reaches the claim denominator.

    No execution re-derives a sample size. A `412` counted as a bindable claim would
    sit in the Phase 0 coverage fraction as an item that can never bind, and pull the
    gate number down for a reason unrelated to how well Plumb works.
    """

    def test_the_claim_output_contains_no_claim_for_the_sample_size(self) -> None:
        claims = claims_of(PAPER)

        assert claims, "nothing was admitted at all; the test is vacuous"
        assert not [claim for claim in claims if claim.reported_value.text == "412"]

    def test_no_reported_size_in_the_document_becomes_a_claim(self) -> None:
        reported = {p.value.text for p in study_parameters(PAPER)}
        admitted = {claim.reported_value.text for claim in claims_of(PAPER)}

        assert reported
        assert not (reported & admitted)

    def test_the_gate_refuses_the_sample_size_with_the_named_cause(self) -> None:
        """Positively, not by absence. The refusal is a record with a cause."""
        text = normalize_text(PAPER)
        refusals = [
            result
            for candidate in extract_candidates(text)
            if candidate.text == "412"
            and isinstance(
                result := admit(candidate, normalized_text=text, metric="AUC"),
                NonClaim,
            )
        ]

        assert len(refusals) == 1
        assert refusals[0].cause == CAUSE_STUDY_PARAMETER
        assert refusals[0].text == "412"

    @pytest.mark.parametrize("document", RECOGNISED)
    def test_no_recognised_form_ever_becomes_a_claim(self, document: str) -> None:
        """The generalised invariant, and the one whose absence let `_n_` through.

        The earlier version of this class checked only one fixture paper, so a
        spelling the recogniser did not know about was tested for *non-recognition*
        and never for what happened to it next. `_n_ = 412` went unrecognised and was
        therefore admitted as a `Claim` — a permanently unbindable item in the very
        denominator M11 exists to protect. An unrecognised N does not fall out of the
        pipeline, it falls through it.

        Asserting over every recognised form ties the two halves together: whatever
        `study_parameters` takes, the claim output must not also contain.
        """
        parameter = only(study_parameters(document))
        claims = claims_of(document, metric="cohort size")

        assert parameter.value.text == "412"
        assert not [c for c in claims if c.reported_value.text == "412"]

    def test_the_real_claim_in_the_same_sentence_still_admits(self) -> None:
        # The control that keeps the test above from passing by refusing everything.
        assert [claim.reported_value.text for claim in claims_of(PAPER)] == ["0.87"]


class TestTheTwoCallersAgree:
    """One recogniser, so the emitter and the gate cannot disagree about what N is.

    If they could, a number would be extracted as neither a parameter nor a claim —
    the silent drop the plan's D2 forbids, and invisible to both outputs.
    """

    DOCUMENTS = (
        PAPER,
        "n = 412, and separately N=1,024 and a stray 99.\n",
        "The median = 412 across sites, with n=7.\n",
        "AUC 0.87 with no cohort size reported at all.\n",
    )

    @pytest.mark.parametrize("document", DOCUMENTS)
    def test_what_the_emitter_takes_is_what_the_gate_refuses(
        self, document: str
    ) -> None:
        text = normalize_text(document)
        emitted = {
            (p.location.start, p.location.end) for p in study_parameters(document)
        }
        refused = {
            (candidate.span.start, candidate.span.end)
            for candidate in extract_candidates(text)
            if isinstance(
                result := admit(candidate, normalized_text=text, metric="AUC"),
                NonClaim,
            )
            and result.cause == CAUSE_STUDY_PARAMETER
        }

        assert emitted == refused

    @pytest.mark.parametrize("document", DOCUMENTS)
    def test_every_number_is_a_parameter_or_a_claim_or_a_named_refusal(
        self, document: str
    ) -> None:
        text = normalize_text(document)
        results = [
            admit(candidate, normalized_text=text, metric="AUC")
            for candidate in extract_candidates(text)
        ]

        assert len(results) == len(extract_candidates(text))
        assert all(isinstance(r, (Claim, NonClaim)) for r in results)


class TestTheNumberGrammarsAgree:
    """`study_parameters` skips a number `parse_value` cannot read. Pin that away.

    The skip is the one path in that function that drops a number without recording
    anything, and it is reachable only if `candidates.py` and `value.py` disagree about
    what a number is. This asserts they do not, over every shape either module names,
    so the branch stays unreachable rather than merely untested.
    """

    CORPUS = (
        "Values: 412, 0.87, .001, 1,024, 12,345,678, 1e-5, 1E+5, 0.0, 10.\n"
        "Signed: -0.5 and +5 and 2.5e-3 in prose.\n"
        "Versions: v1.2.3, 2026, page 7, ref 12.\n"
    )

    def test_every_candidate_the_extractor_finds_parses_as_a_value(self) -> None:
        candidates = extract_candidates(self.CORPUS)

        assert len(candidates) > 15, "the corpus is too thin to prove anything"
        for candidate in candidates:
            assert parse_value(candidate.text) is not None, candidate


class TestNormalizationAndDeterminism:
    """The document-level contract: normalize once, index that, same answer twice."""

    def test_a_crlf_paper_gives_the_same_parameters_as_its_lf_twin(self) -> None:
        """`study_parameters` takes *raw* text and normalizes, like the other
        document-level entry points in this package. `admit` does not, because it is
        called once per candidate and normalizing there would be quadratic.
        """
        crlf = PAPER.replace("\n", "\r\n")

        assert study_parameters(crlf) == study_parameters(PAPER)

    def test_the_offsets_index_the_normalized_text(self) -> None:
        crlf = PAPER.replace("\n", "\r\n")
        text = normalize_text(crlf)

        for parameter in study_parameters(crlf):
            start, end = parameter.location.start, parameter.location.end
            assert text[start:end] == parameter.value.text

    def test_the_same_document_gives_equal_records_twice(self) -> None:
        assert study_parameters(PAPER) == study_parameters(PAPER)

    def test_the_output_is_in_document_order(self) -> None:
        parameters = study_parameters(PAPER)

        starts = [p.location.start for p in parameters]
        assert starts == sorted(starts)

    def test_the_output_is_a_tuple(self) -> None:
        # A list would invite a caller to sort it in place and lose the contract.
        assert isinstance(study_parameters(PAPER), tuple)


class TestMalformedInput:
    """A recogniser that throws partway through a paper loses the rest of the paper."""

    @pytest.mark.parametrize(
        "document",
        [
            "",
            "\n",
            "n =",
            "n = ",
            "= 412",
            "n",
            "412",
            "n = 412",
            "|n|412|\n|---|---|\n",
            "n = 0.5 of the sample\n",
        ],
    )
    def test_it_never_raises(self, document: str) -> None:
        assert isinstance(study_parameters(document), tuple)

    def test_a_document_ending_immediately_after_the_equals_sign(self) -> None:
        assert study_parameters("n =") == ()

    def test_a_number_at_offset_zero(self) -> None:
        # Boundary: the look-behind window starts at 0 and must not wrap around.
        assert study_parameters("412 patients.\n") == ()
