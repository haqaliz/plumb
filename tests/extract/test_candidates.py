"""Tests for candidate extraction: every number in a paper, with its context.

Two properties are asserted here more often than anything else, because they are what
the later selection rule is measured against:

1. **Exhaustive.** Every number is found — years, page numbers, DOIs, version strings
   and list markers included. The counts below are *exact sets*, not lower bounds: an
   "at least N" assertion cannot tell over-extraction (correct, by design) from silent
   filtering (a selection decision this phase is forbidden to make, plan §0).
2. **Judgement-free.** Nothing here decides which numbers are claims, and no test
   asserts a verdict of any kind.

Section hints are structural. They come from Markdown headings and from table
membership, never from what a number appears to mean, so a paper with no headings gets
`other` everywhere — honest, rather than guessed.
"""

from dataclasses import FrozenInstanceError
import time

import pytest

from plumb.extract.candidates import (
    SECTION_ABSTRACT,
    SECTION_HINTS,
    SECTION_OTHER,
    SECTION_REFERENCES,
    SECTION_RESULTS,
    SECTION_TABLE,
    Candidate,
    extract_candidates,
)
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.ordering import location_sort_key
from plumb.extract.value import (
    Approximate,
    Bound,
    Interval,
    PlusMinus,
    Range,
    parse_value,
)

# One paper exercising every structural case at once: numbers in prose, in a table, in
# a heading, in a reference list; a subheading that must inherit its parent's section;
# and the same value (`0.87`) reported twice in two different places.
PAPER = """\
# A Paper About Numbers

## Abstract

We report an AUC of 0.87 in 412 patients.

## Results

Accuracy reached 91.5% and the effect held at p < .001.

| Metric | Value |
|--------|-------|
| AUC    | 0.87  |

### Secondary outcome

The margin was 0.85 ± 0.03.

## Table 2 notes

Nothing further.

## References

1. Smith et al., Journal, 2019, pages 10-12.
"""

#: Every number in `PAPER`, in the order the extractor must emit them, with the hint
#: each one must carry. Written out in full on purpose — see this module's docstring.
EXPECTED = (
    ("0.87", SECTION_ABSTRACT),
    ("412", SECTION_ABSTRACT),
    ("91.5", SECTION_RESULTS),
    ("< .001", SECTION_RESULTS),
    ("0.87", SECTION_TABLE),
    ("0.85 ± 0.03", SECTION_RESULTS),
    ("2", SECTION_OTHER),
    ("1", SECTION_REFERENCES),
    ("2019", SECTION_REFERENCES),
    ("10", SECTION_REFERENCES),
    ("12", SECTION_REFERENCES),
)


def texts_of(document: str) -> tuple[str, ...]:
    return tuple(candidate.text for candidate in extract_candidates(document))


def hints_of(document: str) -> tuple[str, ...]:
    return tuple(candidate.section_hint for candidate in extract_candidates(document))


class TestEveryNumberIsFound:
    def test_the_full_set_of_candidates_is_exact(self) -> None:
        found = tuple(
            (candidate.text, candidate.section_hint)
            for candidate in extract_candidates(PAPER)
        )

        assert found == EXPECTED

    def test_numbers_inside_a_table_are_found(self) -> None:
        in_table = [
            candidate
            for candidate in extract_candidates(PAPER)
            if candidate.section_hint == SECTION_TABLE
        ]

        assert [candidate.text for candidate in in_table] == ["0.87"]

    def test_numbers_inside_a_reference_list_are_found(self) -> None:
        # A reference list is nothing but non-claim numbers, and they are all extracted
        # anyway: deciding they are not claims is selection, and selection does not
        # exist yet (plan §0).
        in_references = [
            candidate.text
            for candidate in extract_candidates(PAPER)
            if candidate.section_hint == SECTION_REFERENCES
        ]

        assert in_references == ["1", "2019", "10", "12"]

    def test_a_number_in_a_heading_is_found(self) -> None:
        heading = [
            candidate
            for candidate in extract_candidates(PAPER)
            if candidate.context.startswith("## Table")
        ]

        assert [candidate.text for candidate in heading] == ["2"]

    def test_the_same_value_reported_twice_yields_two_candidates(self) -> None:
        repeated = [
            candidate for candidate in extract_candidates(PAPER)
            if candidate.text == "0.87"
        ]

        assert len(repeated) == 2
        assert repeated[0].span != repeated[1].span
        assert repeated[0].span.end <= repeated[1].span.start

    def test_nothing_obviously_non_claim_is_filtered_out(self) -> None:
        # Years, DOIs, version strings and page numbers all survive. The exact
        # tokenization is pinned rather than described: a number never starts inside a
        # run of digits (so `412` is one candidate, not three), which is what splits
        # `v1.2.3` into `1.2` and `3` and leaves the DOI's two digit groups separate.
        noisy = "Version v1.2.3, 2019, doi:10.1234/xyz.5678, page 42.\n"

        assert texts_of(noisy) == ("1.2", "3", "2019", "10.1234", "5678", "42")

    def test_a_negative_number_keeps_its_sign_and_a_hyphenated_name_does_not(
        self,
    ) -> None:
        # The sign is part of the number when nothing word-like precedes it, and is a
        # hyphen otherwise. Both readings are judgements; this is the one that keeps
        # `12-15` from becoming `12` and `-15`.
        assert texts_of("The effect was -0.5 overall.\n") == ("-0.5",)
        assert texts_of("AUC-0.87 across 12-15 sites.\n") == ("0.87", "12", "15")


def parsed_of(document: str) -> tuple[tuple[str, str], ...]:
    """Each candidate's text with the `ClaimValue` variant `parse_value` reads from it.

    The pairing is the point. Asserting the text alone would let a composite through
    that looks right and parses to `None`, and asserting the variant alone would not
    say which characters the span covers.
    """
    return tuple(
        (candidate.text, type(parse_value(candidate.text)).__name__)
        for candidate in extract_candidates(document)
    )


class TestCompositeValues:
    """A value the paper wrote as one thing is one candidate, not its pieces.

    This is a tokenization change, not selection: it changes *what counts as one
    number*, and nothing here decides which numbers are claims. The pieces do not
    survive alongside the whole — a `0.001` emitted next to `p < 0.001` would be
    counted twice by any later metric, and admitted on its own it would assert
    `p = 0.001`, a number the paper never wrote.

    Two asymmetries are deliberate and pinned below:

    - A **trailing** `%` stays out of the candidate, exactly as it does for a bare
      number: `12–15%` yields `12–15`, and the unit belongs to `Claim.units`.
    - The **leading** `95%` of `95% CI [0.81, 0.93]` is *inside* the candidate. It is
      not a unit but the confidence level, and `Interval` states that it must never
      surface as an endpoint or as a `Point` of its own — which is precisely what
      leaving it outside would do.
    """

    @pytest.mark.parametrize(
        ("sentence", "text", "variant"),
        [
            (
                "AUC was 0.87 (95% CI [0.81, 0.93]).\n",
                "95% CI [0.81, 0.93]",
                Interval,
            ),
            ("Effect held at p < 0.001.\n", "< 0.001", Bound),
            ("Accuracy 0.85 ± 0.03 overall.\n", "0.85 ± 0.03", PlusMinus),
            ("Range was 12–15% across sites.\n", "12–15", Range),
            ("About ~10,000 reads per sample.\n", "~10,000", Approximate),
        ],
    )
    def test_a_composite_is_one_candidate_of_the_right_variant(
        self, sentence: str, text: str, variant: type
    ) -> None:
        candidates = extract_candidates(sentence)
        composite = next(c for c in candidates if c.text == text)

        assert isinstance(parse_value(composite.text), variant)

    @pytest.mark.parametrize(
        ("sentence", "expected"),
        [
            # The `0.87` beside the interval is a value in its own right and stays a
            # candidate; the `95`, `0.81` and `0.93` inside it do not.
            (
                "AUC was 0.87 (95% CI [0.81, 0.93]).\n",
                (("0.87", "Point"), ("95% CI [0.81, 0.93]", "Interval")),
            ),
            ("Effect held at p < 0.001.\n", (("< 0.001", "Bound"),)),
            ("Accuracy 0.85 ± 0.03 overall.\n", (("0.85 ± 0.03", "PlusMinus"),)),
            ("Range was 12–15% across sites.\n", (("12–15", "Range"),)),
        ],
    )
    def test_no_piece_of_a_composite_is_emitted_beside_it(
        self, sentence: str, expected: tuple[tuple[str, str], ...]
    ) -> None:
        # An exact set, not a membership check: over-emitting the pieces is the
        # failure this change exists to remove, and it is invisible to `in`.
        assert parsed_of(sentence) == expected

    def test_a_bare_number_is_still_a_point(self) -> None:
        # The control. Widening must not reach a number that stands on its own.
        assert parsed_of("The AUC was 0.87 overall.\n") == (("0.87", "Point"),)

    def test_every_composite_span_reproduces_its_own_text(self) -> None:
        document = (
            "AUC 0.87 (95% CI [0.81, 0.93]), p < 0.001, 0.85 ± 0.03, 12–15%, ~10,000.\n"
        )
        normalized = normalize_text(document)

        for candidate in extract_candidates(document):
            assert normalized[candidate.span.start : candidate.span.end] == (
                candidate.text
            )

    def test_adjacent_composites_in_one_sentence_separate(self) -> None:
        document = "Recall 0.85 ± 0.03 at p < 0.001 over 12–15% of sites.\n"

        assert parsed_of(document) == (
            ("0.85 ± 0.03", "PlusMinus"),
            ("< 0.001", "Bound"),
            ("12–15", "Range"),
        )

    def test_an_interval_does_not_swallow_a_neighbouring_number(self) -> None:
        # The number before it and the number after it are both untouched: a
        # composite may only consume the notation it is made of.
        document = "We saw 0.87 (95% CI [0.81, 0.93]) and then 0.91 later.\n"

        assert parsed_of(document) == (
            ("0.87", "Point"),
            ("95% CI [0.81, 0.93]", "Interval"),
            ("0.91", "Point"),
        )

    def test_the_confidence_level_is_not_a_candidate_of_its_own(self) -> None:
        # `Interval` states it: the 95 of `95% CI` is a property of the estimator, and
        # a `Point(95)` from it is a value the paper never reported.
        assert "95" not in texts_of("AUC 0.87 (95% CI [0.81, 0.93]).\n")

    def test_a_trailing_percent_stays_outside_the_candidate(self) -> None:
        # Same rule as a bare number: `91.5%` is `91.5`, so `12–15%` is `12–15`.
        assert texts_of("Between 12–15% of cases.\n") == ("12–15",)
        assert texts_of("Recall 0.85 ± 0.03% overall.\n") == ("0.85 ± 0.03",)

    def test_an_interval_takes_both_endpoint_percents_or_neither(self) -> None:
        # A `%` *between* the endpoints is interior notation and must be kept, or the
        # text would not round-trip as written. A `%` only at the end is a trailing
        # unit like any other, and stays out — the same rule as `12–15%`.
        assert texts_of("Pooled (95% CI: 0.4%-1.7%) overall.\n") == (
            "95% CI: 0.4%-1.7%",
        )
        assert texts_of("Pooled (95% CI: 0.4-1.7%) overall.\n") == (
            "95% CI: 0.4-1.7",
        )

    @pytest.mark.parametrize(
        ("sentence", "text"),
        [
            ("Threshold p<0.001 here.\n", "<0.001"),
            ("Heterogeneity was > 97 percent.\n", "> 97"),
            ("Needs R >= 3.5 installed.\n", ">= 3.5"),
            ("With FDR ≤0.05 applied.\n", "≤0.05"),
            ("At dCor ≥ 0.0884 overall.\n", "≥ 0.0884"),
        ],
    )
    def test_every_operator_spelling_is_kept(self, sentence: str, text: str) -> None:
        # All five spellings occur in the fixture corpus. `>=` must beat `>`, or the
        # candidate would be `> = 3.5` — which parses to nothing.
        assert texts_of(sentence) == (text,)
        assert isinstance(parse_value(text), Bound)

    def test_the_bound_does_not_absorb_the_name_in_front_of_it(self) -> None:
        # `parse_value` would accept `p < 0.001`, and the candidate is still
        # deliberately `< 0.001`: the name is the *metric*, a field of its own that
        # `admit` is given separately. Baking it into the value's verbatim text would
        # let `reported_value.text` name one quantity while `Claim.metric` names
        # another, with nothing to catch the disagreement.
        assert texts_of("Effect held at p < 0.001.\n") == ("< 0.001",)


class TestCompositesAreNotGuessed:
    """The forms that look composite and are not, each one measured in the corpus.

    Every case here would, if widened, merge two numbers the paper kept apart —
    inventing a value rather than recording one. The rule these share: a composite is
    emitted only where `value.py` would parse it, so extraction can never hand
    `admit` a span that `parse_value` then refuses.
    """

    def test_a_percent_sign_blocks_the_minus_that_follows_it(self) -> None:
        """The sign rule's hole, and the false value it produced.

        `+`/`-` joins a number when nothing *word-like* precedes it, and `%` is not
        word-like — so in `0.4%-1.7%` the hyphen was read as a minus and the upper
        endpoint came out `-1.7`, a negative number from a paper reporting a positive
        one. It grounded, it parsed, and `admit` had no reason to refuse it: a
        sign-flipped `Point(-1.7)` entered the record as a claim. A minus sign cannot
        directly follow a percent sign in any notation, so `%` blocks attachment.
        """
        assert texts_of("Values ran 0.4%-1.7% overall.\n") == ("0.4", "1.7")

    @pytest.mark.parametrize(
        ("sentence", "expected"),
        [
            ("The effect was -0.5 overall.\n", ("-0.5",)),
            ("Bounds were (-5.432, -4.092) here.\n", ("-5.432", "-4.092")),
            ("-0.71 was the correlation.\n", ("-0.71",)),
            ("Change of -24.0 and then -0.04.\n", ("-24.0", "-0.04")),
            ("Slope: -1.14 overall.\n", ("-1.14",)),
        ],
    )
    def test_the_sign_rule_still_attaches_everywhere_it_should(
        self, sentence: str, expected: tuple[str, ...]
    ) -> None:
        # Blocking `%` must not cost a real negative. Every shape the sign rule
        # exists for — after a space, after an opening bracket, at the start of the
        # text, after a colon — keeps its sign.
        assert texts_of(sentence) == expected

    def test_a_hyphen_is_not_a_range_separator(self) -> None:
        # `value.py` accepts only en/em dashes, because `12-15` is ambiguous against a
        # signed value; widening on a hyphen here would emit a candidate `parse_value`
        # returns `None` for, turning a known recall gap into an `unparsed_value`
        # refusal. The gap stays where aspect 1 put it.
        assert texts_of("Range was 12-15% across sites.\n") == ("12", "15")
        assert parse_value("12-15") is None

    @pytest.mark.parametrize(
        ("sentence", "text"),
        [
            ("Pooled 1.0% (95% CI: 0.4%-1.7%).\n", "95% CI: 0.4%-1.7%"),
            ("Ratio 1.97 (95% CI: 1.66–2.54) held.\n", "95% CI: 1.66–2.54"),
            ("Slope (95% CI: -5.432, -4.092) fell.\n", "95% CI: -5.432, -4.092"),
            ("Odds (95% CrI: 0.75%-4.1%) rose.\n", "95% CrI: 0.75%-4.1%"),
            ("AUC (95% CI 0.962–0.998) held.\n", "95% CI 0.962–0.998"),
        ],
    )
    def test_the_confidence_intervals_real_papers_write_are_one_candidate(
        self, sentence: str, text: str
    ) -> None:
        # None of the 29 confidence intervals in the corpus is bracketed. These are
        # the forms that occur, and each is one value.
        composite = next(c for c in extract_candidates(sentence) if c.text == text)

        assert isinstance(parse_value(composite.text), Interval)
        assert normalize_text(sentence)[
            composite.span.start : composite.span.end
        ] == composite.text

    def test_a_marked_interval_swallows_its_own_confidence_level(self) -> None:
        # The `Point(95)` escape, closed. Before the whole notation was one
        # candidate, the confidence level stood free as a reported value of its own —
        # and it grounded, so `admit` had no reason to refuse it.
        assert parsed_of("Pooled 1.0% (95% CI: 0.4%-1.7%).\n") == (
            ("1.0", "Point"),
            ("95% CI: 0.4%-1.7%", "Interval"),
        )

    @pytest.mark.parametrize(
        ("sentence", "expected"),
        [
            # A citation pair and a degrees-of-freedom pair. Both parse as `Interval`
            # if handed to `parse_value` on their own, and both are two numbers the
            # paper never joined — so the `CI` marker, not the bracket, is what makes
            # an interval here.
            ("Prior work [30,31] agrees.\n", ("30", "31")),
            ("The model F (6,12) = 15.16 held.\n", ("6", "12", "15.16")),
        ],
    )
    def test_a_bracketed_pair_without_a_ci_marker_is_two_numbers(
        self, sentence: str, expected: tuple[str, ...]
    ) -> None:
        assert texts_of(sentence) == expected

    def test_a_labelled_span_is_not_a_range(self) -> None:
        # `(A1–A22)` occurs in the fixtures. The dash separates two *labels*, and the
        # second operand does not start with a digit, so no range is read.
        assert texts_of("Measurements (A1–A22) were taken.\n") == ("1", "22")

    def test_a_composite_never_crosses_a_line_break(self) -> None:
        # Only spaces and tabs may sit inside a composite. A number ending one line
        # and a dash opening the next is a coincidence of wrapping, not a range, and a
        # span that crossed the break would also cross a table row or a cell boundary.
        assert texts_of("The value was 12\n–15 overall.\n") == ("12", "15")
        assert texts_of("| a | 0.85 |\n|---|---|\n| b | ± 0.03 |\n") == (
            "0.85",
            "0.03",
        )

    def test_a_blockquote_marker_is_not_a_bound(self) -> None:
        # `> 97` opening a line is Markdown quoting, not an operator, and reading it
        # as `Bound(> 97)` would assert a comparison the paper never made.
        assert texts_of("Quoted below:\n\n> 97 patients were enrolled.\n") == ("97",)

    def test_an_arrow_is_not_a_bound(self) -> None:
        assert texts_of("Stage 1 -> 2 was skipped.\n") == ("1", "2")

    def test_a_dash_used_as_prose_punctuation_is_not_a_range(self) -> None:
        # Every one of the 66 dash ranges in the fixture corpus is written tight; a
        # spaced em dash in a paper is punctuation. Requiring tightness costs nothing
        # measured and removes the whole false-positive class.
        assert texts_of("In 2019 — 0.87 was the best score.\n") == ("2019", "0.87")

    def test_a_dash_chain_of_three_numbers_is_not_a_range(self) -> None:
        # `Accessed: 2025–12–18` is in the fixture corpus: an ISO date whose hyphens
        # were typographically converted to en dashes. Two numbers joined by a dash
        # are a range; three are not, and taking the first two would emit
        # `Range(2025, 12)` — a value read out of a date. The guard runs at both ends,
        # or the scan would simply pick the chain's *second* pair instead.
        assert texts_of("Accessed: 2025–12–18 online.\n") == ("2025", "12", "18")

    def test_a_page_range_becomes_one_range_candidate(self) -> None:
        # The stated consequence of the tokenization change, not an oversight: a page
        # range really is one value written with a dash, and nothing is dropped. Both
        # endpoints were already refused as `partial_value` before this change, so no
        # claim is gained or lost — only the counting changes.
        assert parsed_of("1. Smith, Journal, 2019, pages 220–223.\n") == (
            ("1", "Point"),
            ("2019", "Point"),
            ("220–223", "Range"),
        )


class TestSpansRoundTrip:
    def test_every_span_reproduces_its_own_text(self) -> None:
        normalized = normalize_text(PAPER)

        for candidate in extract_candidates(PAPER):
            assert normalized[candidate.span.start : candidate.span.end] == (
                candidate.text
            )

    def test_a_crlf_document_yields_identical_candidates(self) -> None:
        assert extract_candidates(PAPER.replace("\n", "\r\n")) == extract_candidates(
            PAPER
        )


class TestContext:
    def _context_of(self, document: str, text: str) -> str:
        return next(
            candidate.context
            for candidate in extract_candidates(document)
            if candidate.text == text
        )

    def test_prose_context_is_the_surrounding_sentence(self) -> None:
        assert self._context_of(PAPER, "412") == (
            "We report an AUC of 0.87 in 412 patients."
        )
        assert self._context_of(PAPER, "91.5") == (
            "Accuracy reached 91.5% and the effect held at p < .001."
        )

    def test_table_context_is_the_cell_not_the_sentence(self) -> None:
        in_table = next(
            candidate
            for candidate in extract_candidates(PAPER)
            if candidate.section_hint == SECTION_TABLE
        )

        assert in_table.context == "0.87"

    def test_a_heading_is_its_own_context_whole(self) -> None:
        # A heading is a title, not prose: it has no sentences to split. Running the
        # sentence splitter over it truncates `## 3. Results` at the enumerator's
        # period and hands the labeller `## 3.` as the entire context for `3`.
        document = "## 3. Results ##\n\nWe got 0.87.\n"

        assert self._context_of(document, "3") == "## 3. Results ##"

    def test_a_heading_does_not_leak_into_the_sentence_below_it(self) -> None:
        # No blank line between the two, which is legal Markdown. A block that ran
        # from the heading into the paragraph would put `## Results` in front of every
        # context in the section.
        document = "## Results\nThe AUC was 0.87.\n"

        assert self._context_of(document, "0.87") == "The AUC was 0.87."

    def test_context_does_not_run_past_a_blank_line(self) -> None:
        document = "First para has 1 number.\n\nSecond para has 2 numbers.\n"

        assert self._context_of(document, "1") == "First para has 1 number."
        assert self._context_of(document, "2") == "Second para has 2 numbers."

    def test_a_hard_wrapped_sentence_is_one_context(self) -> None:
        document = "The accuracy was\n0.87 across every\nsite.\n"

        assert self._context_of(document, "0.87") == (
            "The accuracy was\n0.87 across every\nsite."
        )

    def test_a_list_marker_does_not_end_a_sentence(self) -> None:
        # `1.` opening a reference is an enumerator, not a full stop. Splitting there
        # leaves the first candidate of every reference with `1.` as its whole context.
        assert self._context_of(PAPER, "2019") == (
            "1. Smith et al., Journal, 2019, pages 10-12."
        )
        assert self._context_of(PAPER, "1") == (
            "1. Smith et al., Journal, 2019, pages 10-12."
        )

    def test_an_initial_and_a_page_abbreviation_do_not_end_a_sentence(self) -> None:
        # A real reference line, which is where the sentence splitter is under the
        # most pressure: an enumerator, an author initial, `et al.` and `pp.` all
        # look like full stops. Splitting at each leaves candidates whose context is
        # `1. Smith, J.` — true, and useless to whoever has to label them.
        document = (
            "## References\n\n"
            "1. Smith, J. et al. Prior work. Journal 12(3), 2019, pp. 10-24.\n"
        )

        assert self._context_of(document, "1") == "1. Smith, J. et al. Prior work."
        assert self._context_of(document, "2019") == (
            "Journal 12(3), 2019, pp. 10-24."
        )
        assert self._context_of(document, "24") == "Journal 12(3), 2019, pp. 10-24."

    def test_a_decimal_point_does_not_end_a_sentence(self) -> None:
        document = "We saw 0.87 and 0.91 in turn. Then nothing.\n"

        assert self._context_of(document, "0.91") == "We saw 0.87 and 0.91 in turn."

    def test_two_sentences_in_one_paragraph_get_their_own_contexts(self) -> None:
        document = "The AUC was 0.87. The recall was 0.91.\n"

        assert self._context_of(document, "0.87") == "The AUC was 0.87."
        assert self._context_of(document, "0.91") == "The recall was 0.91."


class TestSectionHints:
    def test_hints_come_from_headings(self) -> None:
        document = (
            "## Abstract\n\nWe saw 1.\n\n"
            "## Methods\n\nWe did 2.\n\n"
            "## Results\n\nWe got 3.\n\n"
            "## References\n\nSee 4.\n"
        )

        assert hints_of(document) == (
            SECTION_ABSTRACT,
            SECTION_OTHER,
            SECTION_RESULTS,
            SECTION_REFERENCES,
        )

    def test_a_numbered_or_closed_heading_still_maps(self) -> None:
        # `## 3. Results ##` is the same heading as `## Results`; the enumerator and
        # the closing hashes are Markdown syntax. Note the enumerator's own `3` is a
        # candidate too, and sits in the section its heading opens.
        document = "## 3. Results ##\n\nWe got 0.87.\n"

        assert texts_of(document) == ("3", "0.87")
        assert hints_of(document) == (SECTION_RESULTS, SECTION_RESULTS)

    def test_a_subheading_inherits_its_parent_section(self) -> None:
        # Structural, by heading level — not by reading the subheading's words.
        assert self._hint_of(PAPER, "0.85 ± 0.03") == SECTION_RESULTS

    def test_a_sibling_heading_ends_the_section(self) -> None:
        assert self._hint_of(PAPER, "2") == SECTION_OTHER

    def test_a_document_with_no_headings_is_all_other(self) -> None:
        document = "We report an AUC of 0.87 in 412 patients over 12 sites.\n"

        assert hints_of(document) == (SECTION_OTHER,) * 3

    def test_a_table_wins_over_the_section_it_sits_in(self) -> None:
        # `table` is the more specific structural container, and it is the one that
        # says how the context should be read.
        document = "## References\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"

        assert hints_of(document) == (SECTION_TABLE, SECTION_TABLE)

    def test_every_hint_is_from_the_allowed_set(self) -> None:
        assert SECTION_HINTS == frozenset(
            {"abstract", "results", "table", "references", "other"}
        )
        for candidate in extract_candidates(PAPER):
            assert candidate.section_hint in SECTION_HINTS

    def _hint_of(self, document: str, text: str) -> str:
        return next(
            candidate.section_hint
            for candidate in extract_candidates(document)
            if candidate.text == text
        )


class TestDeterminism:
    def test_the_same_document_yields_the_same_candidates_twice(self) -> None:
        assert extract_candidates(PAPER) == extract_candidates(PAPER)

    def test_candidates_are_ordered_by_the_shared_location_key(self) -> None:
        candidates = extract_candidates(PAPER)
        keys = [location_sort_key(candidate.span) for candidate in candidates]

        assert keys == sorted(keys)

    def test_an_empty_document_yields_nothing(self) -> None:
        assert extract_candidates("") == ()
        assert extract_candidates("No numbers here at all.\n") == ()


class TestCostIsLinearInTheDocument:
    """A paper is thousands of lines and thousands of numbers, not a fixture.

    Both of the obvious implementations are quadratic: re-deriving a candidate's
    enclosing paragraph by walking outwards from its line, and re-splitting that
    paragraph into sentences, once per number. On a 4000-line paper that is ~22
    seconds — and it never shows up in a fixture-sized test, because the fixtures are
    twenty lines long.

    The bound is deliberately loose (a linear pass is well under a tenth of a second
    here, a quadratic one is hundreds of times over) so this is a shape test rather
    than a benchmark, and cannot go flaky on a slow machine.
    """

    def test_a_paper_sized_document_extracts_in_linear_time(self) -> None:
        paper = "## Results\n\n" + (
            "The AUC was 0.87 in 412 patients across 12 sites.\n" * 4000
        )

        start = time.perf_counter()
        candidates = extract_candidates(paper)
        elapsed = time.perf_counter() - start

        assert len(candidates) == 12000
        assert candidates[-1].context == (
            "The AUC was 0.87 in 412 patients across 12 sites."
        )
        assert elapsed < 5.0


class TestTheRecordIsSealed:
    def _candidate(self) -> Candidate:
        return extract_candidates(PAPER)[0]

    def test_a_candidate_is_frozen(self) -> None:
        with pytest.raises(FrozenInstanceError):
            self._candidate().text = "other"  # type: ignore[misc]

    def test_a_candidate_rejects_an_extra_attribute(self) -> None:
        # No `__dict__`, so no `confidence` can be attached later (`CLAUDE.md` #1).
        with pytest.raises(AttributeError):
            object.__setattr__(self._candidate(), "confidence", "0.9")

    def test_a_candidate_requires_a_char_span(self) -> None:
        with pytest.raises(TypeError):
            Candidate(
                text="0.87",
                span="0:4",  # type: ignore[arg-type]
                context="x",
                section_hint=SECTION_OTHER,
            )

    def test_a_candidate_rejects_an_unknown_section_hint(self) -> None:
        # A closed vocabulary: an invented hint would reach the labelling file and the
        # selection rule as though it were a structural fact.
        with pytest.raises(ValueError):
            Candidate(
                text="0.87",
                span=CharSpan(0, 4),
                context="x",
                section_hint="discussion",
            )
