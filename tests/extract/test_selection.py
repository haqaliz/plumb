"""The claim-selection rule (M3): which candidates are worth admitting.

The gate (`admit.py`) checks grounding and notation; this rule checks *worth* —
section, attribution, named metric — and is scored against labels it did not
author. Every test here asserts a decision and its cause; none asserts a verdict.
"""

from __future__ import annotations

from dataclasses import fields
from typing import ClassVar

import pytest

from plumb.extract.candidates import (
    SECTION_ABSTRACT,
    SECTION_OTHER,
    SECTION_REFERENCES,
    SECTION_RESULTS,
    SECTION_TABLE,
    Candidate,
)
from plumb.extract.location import CharSpan
from plumb.extract.selection import (
    CAUSE_AXIS_LABEL,
    CAUSE_DOI_DIGITS,
    CAUSE_FIGURE_NUMBER,
    CAUSE_HYPERPARAMETER,
    CAUSE_NO_NAMED_METRIC,
    CAUSE_OUTSIDE_SECTIONS,
    CAUSE_REFERENCE_NUMERAL,
    CAUSE_RELATED_WORK,
    CAUSE_VERSION_STRING,
    CAUSE_YEAR,
    SELECTION_CAUSES,
    Selected,
    SelectionRejection,
    metric_of,
    select,
)


def candidate(
    text: str,
    *,
    context: str,
    section_hint: str = SECTION_ABSTRACT,
) -> Candidate:
    start = context.index(text)
    return Candidate(
        text=text,
        span=CharSpan(start, start + len(text)),
        context=context,
        section_hint=section_hint,
    )


def rejected(c: Candidate) -> SelectionRejection:
    outcome = select(c, normalized_text=c.context)
    assert isinstance(outcome, SelectionRejection), (
        f"expected a rejection for {c.text!r}, got {outcome!r}"
    )
    return outcome


def selected(c: Candidate) -> Selected:
    outcome = select(c, normalized_text=c.context)
    assert isinstance(outcome, Selected), (
        f"expected selection for {c.text!r}, got {outcome!r}"
    )
    return outcome


class TestTheCauseVocabulary:
    def test_the_causes_are_a_closed_set_and_distinct_from_the_gates(self) -> None:
        from plumb.extract.admit import NON_CLAIM_CAUSES

        assert SELECTION_CAUSES.isdisjoint(NON_CLAIM_CAUSES)

    def test_every_cause_has_a_module_constant(self) -> None:
        named = {
            CAUSE_REFERENCE_NUMERAL,
            CAUSE_OUTSIDE_SECTIONS,
            CAUSE_YEAR,
            CAUSE_FIGURE_NUMBER,
            CAUSE_VERSION_STRING,
            CAUSE_DOI_DIGITS,
            CAUSE_HYPERPARAMETER,
            CAUSE_AXIS_LABEL,
            CAUSE_RELATED_WORK,
            CAUSE_NO_NAMED_METRIC,
        }
        assert named == SELECTION_CAUSES


class TestRejectionCategories:
    def test_a_publication_year_is_not_a_claim(self) -> None:
        c = candidate("2019", context="In 2019, we recruited participants from the clinic.")
        assert rejected(c).cause == CAUSE_YEAR

    def test_a_citation_year_is_not_a_claim(self) -> None:
        c = candidate("2020", context="The result (Smith et al., 2020) was later replicated.")
        assert rejected(c).cause == CAUSE_YEAR

    def test_a_year_like_count_without_a_date_cue_is_not_rejected_as_a_year(self) -> None:
        c = candidate("2020", context="We enrolled 2020 participants in the study.")
        assert rejected(c).cause == CAUSE_NO_NAMED_METRIC

    def test_a_figure_number_is_not_a_claim(self) -> None:
        c = candidate("3", context="The performance gain is shown in Fig. 3.")
        assert rejected(c).cause == CAUSE_FIGURE_NUMBER

    def test_a_version_string_is_not_a_claim(self) -> None:
        c = candidate("3.9", context="All analyses used Python 3.9.")
        assert rejected(c).cause == CAUSE_VERSION_STRING

    def test_a_dotted_triple_version_is_not_a_claim(self) -> None:
        c = candidate(">= 3.5.0", context="Built with torch (>= 3.5.0).")
        assert rejected(c).cause == CAUSE_VERSION_STRING

    def test_doi_digits_are_not_a_claim(self) -> None:
        c = candidate("10.1007", context="Available at 10.1007/s00439-026-02852-3.")
        assert rejected(c).cause == CAUSE_DOI_DIGITS

    def test_reference_list_numerals_are_not_claims(self) -> None:
        c = candidate("42", context="42. Smith J. A study of things.", section_hint=SECTION_REFERENCES)
        assert rejected(c).cause == CAUSE_REFERENCE_NUMERAL

    def test_a_bracketed_citation_is_not_a_claim(self) -> None:
        c = candidate("30", context="Earlier work [30,31] reported similar results.")
        assert rejected(c).cause == CAUSE_REFERENCE_NUMERAL

    def test_a_hyperparameter_is_not_a_claim(self) -> None:
        c = candidate("32", context="The model was trained with batch size 32 for 50 epochs.")
        assert rejected(c).cause == CAUSE_HYPERPARAMETER

    def test_an_axis_label_is_not_a_claim(self) -> None:
        c = candidate("100", context="The x-axis 0-100 was rescaled before plotting.")
        assert rejected(c).cause == CAUSE_AXIS_LABEL

    def test_a_number_in_the_other_section_is_not_a_claim(self) -> None:
        c = candidate("0.87", context="A value of 0.87 mentioned in passing.",
                      section_hint=SECTION_OTHER)
        assert rejected(c).cause == CAUSE_OUTSIDE_SECTIONS


class TestRelatedWork:
    def test_et_al_attribution_is_not_this_papers_claim(self) -> None:
        c = candidate("0.87", context="Smith et al. reported an AUC of 0.87 in their cohort.")
        assert rejected(c).cause == CAUSE_RELATED_WORK

    def test_a_parenthetical_surname_year_attribution_is_not_a_claim(self) -> None:
        c = candidate("0.87", context="A previous analysis (Smith, 2019) found 0.87.")
        assert rejected(c).cause == CAUSE_RELATED_WORK

    def test_a_vs_comparator_value_is_attributed_to_the_other_result(self) -> None:
        c = candidate("0.061", context="Our Brier 0.049 vs 0.061 outperformed the prior work.")
        assert rejected(c).cause == CAUSE_RELATED_WORK

    def test_the_own_value_in_a_vs_pair_is_not_rejected(self) -> None:
        c = candidate("0.049", context="Our Brier 0.049 vs 0.061 outperformed the prior work.")
        assert selected(c)


class TestTheSampleSizeFallThroughClass:
    def test_n_of_is_not_a_claim(self) -> None:
        c = candidate("412", context="We recruited a total of n of 412 participants.")
        assert rejected(c).cause == CAUSE_NO_NAMED_METRIC

    def test_sample_size_of_is_not_a_claim(self) -> None:
        c = candidate("412", context="The sample size of 412 was fixed before analysis.")
        assert rejected(c).cause == CAUSE_NO_NAMED_METRIC

    def test_a_table_cell_under_an_n_row_is_not_a_claim(self) -> None:
        c = candidate("412", context="412", section_hint=SECTION_TABLE)
        assert rejected(c).cause == CAUSE_NO_NAMED_METRIC

    def test_a_bare_number_without_a_quantity_phrase_is_not_a_claim(self) -> None:
        c = candidate("0.87", context="0.87", section_hint=SECTION_TABLE)
        assert rejected(c).cause == CAUSE_NO_NAMED_METRIC


class TestTheMetricNamer:
    def test_sensitivity_from_preceding_clause(self) -> None:
        assert metric_of(candidate("0.87", context="The sensitivity was 0.87."), normalized_text="The sensitivity was 0.87.") == "sensitivity"

    def test_auc_of(self) -> None:
        assert metric_of(candidate("0.92", context="An AUC of 0.92 was achieved."), normalized_text="An AUC of 0.92 was achieved.") == "AUC"

    def test_interval_metric_from_the_candidate_prefix(self) -> None:
        c = candidate("95% CI: 0.4%-1.7%", context="Prevalence 0.8% (95% CI: 0.4%-1.7%).")
        assert metric_of(c, normalized_text=c.context) == "95% CI"

    def test_p_value_metric(self) -> None:
        c = candidate("p < 0.001", context="The effect was significant (p < 0.001).")
        assert metric_of(c, normalized_text=c.context) == "p"

    def test_prevalence_estimate(self) -> None:
        assert (
            metric_of(candidate("4.3", context="A prevalence estimate of 4.3% was reported."),
                      normalized_text="A prevalence estimate of 4.3% was reported.")
            == "prevalence estimate"
        )

    def test_no_phrase_yields_none(self) -> None:
        assert metric_of(candidate("412", context="412"), normalized_text="412") is None

    def test_a_metric_that_names_only_a_sample_size_yields_none(self) -> None:
        assert metric_of(candidate("412", context="The sample size of 412 was fixed."), normalized_text="The sample size of 412 was fixed.") is None


class TestUnits:
    def test_a_units_token_after_the_value_is_carried_through(self) -> None:
        outcome = selected(candidate("0.87", context="The weight was 0.87 kg."))
        assert outcome.units == "kg"

    def test_no_units_token_yields_none(self) -> None:
        outcome = selected(candidate("0.87", context="The weight was 0.87."))
        assert outcome.units is None


class TestTheCheckOrder:
    def test_section_reference_beats_a_year_cue(self) -> None:
        c = candidate("2019", context="2019. Some entry in the bibliography.",
                      section_hint=SECTION_REFERENCES)
        assert rejected(c).cause == CAUSE_REFERENCE_NUMERAL

    def test_a_metric_comes_with_the_selection(self) -> None:
        outcome = selected(candidate("0.87", context="The sensitivity was 0.87."))
        assert outcome.metric == "sensitivity"


class TestTheRecord:
    def test_selection_rejection_mirrors_nonclaim_shape(self) -> None:
        from plumb.extract.admit import NonClaim

        rejection_fields = {f.name for f in fields(SelectionRejection)}
        nonclaim_fields = {f.name for f in fields(NonClaim)}
        assert rejection_fields == nonclaim_fields

    def test_a_rejection_carries_the_candidates_text_and_span(self) -> None:
        c = candidate("2019", context="In 2019, we recruited participants.")
        outcome = rejected(c)
        assert outcome.text == "2019"
        assert outcome.location == c.span

    def test_an_unknown_cause_is_refused(self) -> None:
        with pytest.raises(ValueError):
            SelectionRejection(cause="not-a-cause", text="2019", location=CharSpan(0, 4))

    def test_selection_never_returns_a_claim(self) -> None:
        from plumb.extract.claim import Claim

        assert not issubclass(Selected, Claim)
        assert not issubclass(SelectionRejection, Claim)