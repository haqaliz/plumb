"""Tests for the blind labelling file: emitted empty, filled by a human, read back.

The assertion this file exists for is the smallest one in it:
`test_the_label_column_is_empty_on_every_row`. The labels are the yardstick the
selection rule is later measured against (plan §0), so a value the *emitter* wrote into
the label column would be the rule's own opinion coming back as the measurement. That
test is a guardrail, not a detail — if it is ever failing, nothing below it matters.

Everything else here is about the file surviving the trip: real paper prose contains
commas, quotation marks, pipes and line breaks, and a labelling file that mangles any
of them is committed evidence of the wrong context.

No test here asserts a verdict, and no test asserts whether a candidate *is* a claim —
that judgement belongs to the human labeller and, later, to a rule written against
their labels.
"""

import json

import pytest

from plumb.extract.candidates import (
    SECTION_RESULTS,
    Candidate,
    extract_candidates,
)
from plumb.extract.labelling import (
    LABEL_CLAIM,
    LABEL_NOT_CLAIM,
    LABELLING_FORMAT,
    LABELS,
    ROW_FIELDS,
    LabellingError,
    candidate_id,
    emit_labelling_file,
    load_labels,
)
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.ordering import location_sort_key

DOCUMENT = "fixtures/papers/example.md"

PAPER = """\
# A Paper About Numbers

## Abstract

We report an AUC of 0.87 in 412 patients.

## Results

Accuracy reached 91.5% and the effect held at p < .001.

| Metric | Value |
|--------|-------|
| AUC    | 0.87  |

## References

1. Smith, J. et al. Something. Journal, 2019.
"""

#: Every hazard a naive line format gets wrong, in one sentence of plausible prose:
#: commas, double quotes, an unescaped pipe, and a hard wrap that puts a newline
#: *inside* the context a labeller reads.
ADVERSARIAL = """\
## Results

The cohort, "the ones we call `pipe | tolerant`", reached 12,
which is 91.5% of the "target, adjusted" total.
"""

#: One sentence, four identical numbers. A row carrying only `12` and this sentence
#: cannot tell a labeller *which* `12` is meant.
AMBIGUOUS = """\
## Results

Rows 12, 12 and 12 of Table 12 were dropped.
"""


def emit(paper: str, document: str = DOCUMENT) -> bytes:
    return emit_labelling_file(
        extract_candidates(paper), paper=paper, document=document
    )


def lines(data: bytes) -> list[str]:
    return data.decode("utf-8").split("\n")[:-1]


def header(data: bytes) -> dict[str, object]:
    return json.loads(lines(data)[0])


def rows(data: bytes) -> list[dict[str, object]]:
    return [json.loads(line) for line in lines(data)[1:]]


def fill(data: bytes, label: str = LABEL_NOT_CLAIM) -> bytes:
    """The file as a human hands it back: every label column filled in."""
    return rewrite(data, lambda row: {**row, "label": label})


def rewrite(data: bytes, edit) -> bytes:
    """Re-emit the file with `edit` applied to each row — a stand-in for editing."""
    out = [lines(data)[0]]
    out.extend(json.dumps(edit(row), ensure_ascii=False) for row in rows(data))
    return ("\n".join(out) + "\n").encode("utf-8")


class TestTheLabelColumnIsNeverPrefilled:
    """The guardrail. A suggestion in this column is the circularity, back door in.

    The whole ordering — label first, rule second — exists so precision and recall can
    fail. An emitted "likely claim" would anchor the labeller onto the very rule being
    measured, and the measurement would come back agreeing with itself no matter what
    the rule said.
    """

    def test_the_label_column_is_empty_on_every_row(self) -> None:
        emitted = rows(emit(PAPER))
        assert emitted
        assert [row["label"] for row in emitted] == [None] * len(emitted)

    def test_the_column_is_present_and_empty_rather_than_absent(self) -> None:
        # Absent would be "empty" too, and would leave the labeller with nowhere
        # obvious to type. Present-and-null is the contract.
        for row in rows(emit(PAPER)):
            assert "label" in row

    def test_no_label_vocabulary_word_is_written_as_a_label(self) -> None:
        # At the byte level as well as the parsed level: exactly one empty label per
        # row, and no row carrying a value from the vocabulary.
        data = emit(PAPER)
        assert data.count(b'"label": null') == len(rows(data))
        for value in sorted(LABELS):
            assert f'"label": "{value}"'.encode("utf-8") not in data


class TestTheEmittedFile:
    def test_one_header_line_then_one_row_per_candidate(self) -> None:
        candidates = extract_candidates(PAPER)
        data = emit(PAPER)
        assert len(lines(data)) == len(candidates) + 1
        assert header(data)["format"] == LABELLING_FORMAT

    def test_the_header_states_the_label_vocabulary_for_the_labeller(self) -> None:
        # The person filling this in should not have to read the source to learn what
        # they may type.
        assert sorted(LABELS) == header(emit(PAPER))["label_values"]

    def test_every_row_carries_exactly_the_declared_fields(self) -> None:
        for row in rows(emit(PAPER)):
            assert tuple(row) == ROW_FIELDS

    def test_every_row_names_its_source_document(self) -> None:
        # A labelling file merged from two papers must stay attributable per row.
        assert {row["document"] for row in rows(emit(PAPER))} == {DOCUMENT}

    def test_a_row_carries_the_section_hint_and_the_number_itself(self) -> None:
        by_text = {row["text"]: row for row in rows(emit(PAPER))}
        assert by_text["91.5"]["section"] == SECTION_RESULTS
        assert by_text["412"]["section"] == "abstract"

    def test_the_file_is_one_line_per_candidate_even_with_newlines_in_context(
        self,
    ) -> None:
        # The property CSV cannot offer: a context containing a line break still
        # occupies exactly one physical line, so a git diff of one label is one line.
        data = emit(ADVERSARIAL)
        assert len(lines(data)) == len(extract_candidates(ADVERSARIAL)) + 1
        assert any(
            "\n" in row["context_before"] + row["context_after"] for row in rows(data)
        )


class TestTheContextPutInFrontOfTheLabeller:
    """`Candidate.text` is a bare number. The row has to make it judgeable anyway."""

    def test_the_context_halves_reconstruct_the_candidate_context_exactly(self) -> None:
        candidates = extract_candidates(PAPER)
        by_id = {candidate_id(c, document=DOCUMENT): c for c in candidates}
        for row in rows(emit(PAPER)):
            candidate = by_id[row["id"]]
            rebuilt = row["context_before"] + row["text"] + row["context_after"]
            assert rebuilt == candidate.context

    def test_the_split_points_at_the_occurrence_this_row_is_about(self) -> None:
        # Four identical `12`s in one sentence: the halves must differ per row, and
        # each must place the number where that row's span actually sits.
        text = normalize_text(AMBIGUOUS)
        candidates = extract_candidates(AMBIGUOUS)
        assert [c.text for c in candidates] == ["12", "12", "12", "12"]

        emitted = rows(emit(AMBIGUOUS))
        assert len({row["context_before"] for row in emitted}) == 4
        for candidate, row in zip(candidates, emitted):
            context_start = candidate.span.start - len(row["context_before"])
            assert text[context_start:].startswith(candidate.context)
            assert text[
                candidate.span.start : candidate.span.end
            ] == row["text"]

    def test_a_table_cell_candidate_carries_the_cell_as_its_context(self) -> None:
        cells = [row for row in rows(emit(PAPER)) if row["section"] == "table"]
        assert cells
        for row in cells:
            assert row["context_before"] + row["text"] + row["context_after"]

    def test_the_row_carries_the_span_it_was_read_from(self) -> None:
        text = normalize_text(PAPER)
        for row in rows(emit(PAPER)):
            start, end = row["span"]
            assert text[start:end] == row["text"]


class TestRoundTrip:
    def test_a_filled_file_loads_back_as_the_label_set(self) -> None:
        candidates = extract_candidates(PAPER)
        loaded = load_labels(
            fill(emit(PAPER), LABEL_CLAIM),
            candidates=candidates,
            paper=PAPER,
            document=DOCUMENT,
        )
        assert [entry.candidate for entry in loaded] == list(candidates)
        assert {entry.label for entry in loaded} == {LABEL_CLAIM}

    def test_each_label_stays_with_its_own_candidate(self) -> None:
        candidates = extract_candidates(PAPER)
        data = emit(PAPER)
        # Label only the numbers in the abstract, so a mix-up is visible.
        marked = {
            row["id"]
            for row in rows(data)
            if row["section"] == "abstract"
        }
        assert marked
        filled = rewrite(
            data,
            lambda row: {
                **row,
                "label": LABEL_CLAIM if row["id"] in marked else LABEL_NOT_CLAIM,
            },
        )
        for entry in load_labels(
            filled, candidates=candidates, paper=PAPER, document=DOCUMENT
        ):
            abstract = entry.candidate.section_hint == "abstract"
            assert entry.label == (LABEL_CLAIM if abstract else LABEL_NOT_CLAIM)

    def test_an_adversarial_context_survives_the_round_trip_exactly(self) -> None:
        candidates = extract_candidates(ADVERSARIAL)
        context = candidates[0].context
        assert all(character in context for character in (',', '"', "|", "\n"))

        loaded = load_labels(
            fill(emit(ADVERSARIAL)),
            candidates=candidates,
            paper=ADVERSARIAL,
            document=DOCUMENT,
        )
        assert [entry.candidate.context for entry in loaded] == [
            candidate.context for candidate in candidates
        ]

    def test_loaded_entries_are_in_the_emitted_order(self) -> None:
        candidates = extract_candidates(PAPER)
        loaded = load_labels(
            fill(emit(PAPER)), candidates=candidates, paper=PAPER, document=DOCUMENT
        )
        keys = [location_sort_key(entry.candidate.span) for entry in loaded]
        assert keys == sorted(keys)

    def test_a_row_id_is_the_id_derived_from_its_candidate(self) -> None:
        candidates = extract_candidates(PAPER)
        emitted = [row["id"] for row in rows(emit(PAPER))]
        assert emitted == [candidate_id(c, document=DOCUMENT) for c in candidates]


class TestDeterminism:
    def test_the_same_candidates_produce_the_same_bytes(self) -> None:
        assert emit(PAPER) == emit(PAPER)

    def test_input_order_does_not_reach_the_output(self) -> None:
        candidates = extract_candidates(PAPER)
        reversed_input = emit_labelling_file(
            tuple(reversed(candidates)), paper=PAPER, document=DOCUMENT
        )
        assert reversed_input == emit(PAPER)

    def test_the_field_order_is_pinned(self) -> None:
        # Committed evidence: a reordering would rewrite every line of every labelling
        # file in git history's diff, for no change in content.
        assert ROW_FIELDS == (
            "id",
            "document",
            "section",
            "text",
            "span",
            "context_before",
            "context_after",
            "label",
        )
        first = lines(emit(PAPER))[1]
        assert first.index('"id"') < first.index('"label"')

    def test_ids_are_stable_across_calls_and_differ_per_document(self) -> None:
        candidate = extract_candidates(PAPER)[0]
        assert candidate_id(candidate, document=DOCUMENT) == candidate_id(
            candidate, document=DOCUMENT
        )
        assert candidate_id(candidate, document=DOCUMENT) != candidate_id(
            candidate, document="other.md"
        )


class TestTheEmitterRefusesWhatItCannotDescribe:
    def test_a_candidate_that_did_not_come_from_this_paper_is_refused(self) -> None:
        stranger = Candidate(
            text="99",
            span=CharSpan(0, 2),
            context="99 is not in this paper.",
            section_hint=SECTION_RESULTS,
        )
        with pytest.raises(ValueError, match="does not appear in"):
            emit_labelling_file([stranger], paper=PAPER, document=DOCUMENT)

    def test_a_span_that_no_longer_yields_its_text_is_refused(self) -> None:
        # Same context, wrong offsets: the row would show the labeller a number the
        # span does not point at.
        candidate = extract_candidates(PAPER)[0]
        moved = Candidate(
            text=candidate.text,
            span=CharSpan(candidate.span.start + 1, candidate.span.end + 1),
            context=candidate.context,
            section_hint=candidate.section_hint,
        )
        with pytest.raises(ValueError, match="does not appear in"):
            emit_labelling_file([moved], paper=PAPER, document=DOCUMENT)

    def test_an_absolute_document_path_is_refused(self) -> None:
        # The file is committed. A path from the labeller's machine is both noise in
        # the diff and an unnecessary leak of where they keep their papers.
        with pytest.raises(ValueError, match="repo-relative"):
            emit(PAPER, document="/Users/someone/papers/example.md")

    def test_an_empty_document_name_is_refused(self) -> None:
        with pytest.raises(ValueError, match="document"):
            emit(PAPER, document="")


class TestTheLoaderFailsLoudlyAndSpecifically:
    """Every rejection names the line, the row and the repair.

    A labelling file is filled in by hand, so every one of these is a thing that will
    actually happen. A loader that shrugged — skipping the unlabelled row, coercing the
    typo, ignoring the id it did not recognise — would silently shrink or corrupt the
    blind set the rule is scored against, and the score would still look fine.
    """

    def _candidates(self) -> tuple[Candidate, ...]:
        return extract_candidates(PAPER)

    def test_an_unknown_id_is_rejected(self) -> None:
        data = rewrite(emit(PAPER), lambda row: {**row, "label": LABEL_CLAIM})
        broken = data.replace(
            rows(data)[0]["id"].encode("ascii"), b"0000000000000000"
        )
        with pytest.raises(LabellingError, match="unknown row id"):
            load_labels(broken, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_an_unlabelled_row_is_rejected(self) -> None:
        data = emit(PAPER)
        one_short = rewrite(
            data,
            lambda row: {
                **row,
                "label": None if row["id"] == rows(data)[1]["id"] else LABEL_CLAIM,
            },
        )
        with pytest.raises(LabellingError, match="has no label"):
            load_labels(one_short, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_row_with_no_label_field_at_all_is_rejected(self) -> None:
        stripped = rewrite(
            emit(PAPER),
            lambda row: {k: v for k, v in row.items() if k != "label"},
        )
        with pytest.raises(LabellingError, match="missing field"):
            load_labels(stripped, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_an_unparseable_label_value_is_rejected(self) -> None:
        data = rewrite(emit(PAPER), lambda row: {**row, "label": "probably"})
        with pytest.raises(LabellingError, match="unparseable label"):
            load_labels(data, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_label_of_the_wrong_type_is_rejected(self) -> None:
        data = rewrite(emit(PAPER), lambda row: {**row, "label": True})
        with pytest.raises(LabellingError, match="unparseable label"):
            load_labels(data, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_duplicated_row_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        doubled = data + lines(data)[1].encode("utf-8") + b"\n"
        with pytest.raises(LabellingError, match="duplicate row id"):
            load_labels(doubled, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_file_missing_a_candidate_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        kept = [lines(data)[0], *lines(data)[2:]]
        short = ("\n".join(kept) + "\n").encode("utf-8")
        with pytest.raises(LabellingError, match="does not label every candidate"):
            load_labels(short, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_file_emitted_from_another_paper_is_rejected(self) -> None:
        other = fill(emit(ADVERSARIAL))
        with pytest.raises(LabellingError, match="unknown row id"):
            load_labels(other, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_file_emitted_under_another_document_name_is_rejected(self) -> None:
        elsewhere = fill(emit(PAPER, document="fixtures/papers/other.md"))
        with pytest.raises(LabellingError, match="unknown row id"):
            load_labels(elsewhere, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_an_edited_context_is_rejected(self) -> None:
        # Only the label column may be edited. A context quietly reworded in the
        # labelling file would mean the labeller judged text the paper does not say.
        data = fill(emit(PAPER))
        tampered = rewrite(
            data,
            lambda row: {**row, "context_after": row["context_after"] + " (sic)"},
        )
        with pytest.raises(LabellingError, match="no longer matches"):
            load_labels(tampered, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_an_edited_section_hint_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        tampered = rewrite(data, lambda row: {**row, "section": "results"})
        with pytest.raises(LabellingError, match="no longer matches"):
            load_labels(tampered, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_an_unexpected_field_is_rejected(self) -> None:
        # Including the obvious one: a column of predictions helpfully added next to
        # the labels.
        data = rewrite(
            fill(emit(PAPER)), lambda row: {**row, "predicted": LABEL_CLAIM}
        )
        with pytest.raises(LabellingError, match="unexpected field"):
            load_labels(data, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_line_that_is_not_json_is_rejected_with_its_line_number(self) -> None:
        data = fill(emit(PAPER))
        broken = data + b"not json at all\n"
        with pytest.raises(LabellingError, match="line 9"):
            load_labels(broken, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_line_that_is_not_an_object_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        broken = data + b"[1, 2, 3]\n"
        with pytest.raises(LabellingError, match="JSON object"):
            load_labels(broken, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_file_without_the_header_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        headless = ("\n".join(lines(data)[1:]) + "\n").encode("utf-8")
        with pytest.raises(LabellingError, match="labelling file"):
            load_labels(headless, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_a_header_from_a_future_format_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        future = data.replace(
            LABELLING_FORMAT.encode("ascii"), b"plumb.labelling.v99"
        )
        with pytest.raises(LabellingError, match="plumb.labelling.v1"):
            load_labels(future, candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_an_empty_file_is_rejected(self) -> None:
        with pytest.raises(LabellingError, match="labelling file"):
            load_labels(b"", candidates=self._candidates(), paper=PAPER, document=DOCUMENT)

    def test_text_rather_than_bytes_is_refused(self) -> None:
        # Symmetric with the emitter, which returns bytes: an encoding decided at the
        # call site is an encoding nobody pinned.
        with pytest.raises(TypeError, match="bytes"):
            load_labels(
                fill(emit(PAPER)).decode("utf-8"),  # type: ignore[arg-type]
                candidates=self._candidates(),
                paper=PAPER,
                document=DOCUMENT,
            )
