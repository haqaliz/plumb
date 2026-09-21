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
    LabelledCandidate,
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

#: The case a sentence-shaped context cannot carry: inside a table the context is the
#: cell, so `0.840` arrives with nothing around it.
TABLE = """\
| Model    | AUC   | p     |
|----------|-------|-------|
| Baseline | 0.812 | 0.04  |
| Ours     | 0.840 | 0.001 |
"""

#: A header cell the author left blank — "" (a cell that is empty) rather than `null`
#: (no cell at all).
BLANK_HEADER = """\
| Model | |
|-------|--|
| Ours  | 0.840 |
"""

#: A data row with more cells than its header: the last number has no header above it.
RAGGED = """\
| Model | AUC |
|-------|-----|
| Ours  | 0.840 | 0.001 |
"""

#: Numbers in the header row itself, where the column header is the number.
NUMERIC_HEADER = """\
| 2019 | 2020 |
|------|------|
| 12   | 13   |
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

    The whole ordering — label first, rule second — exists so precision and recall
    can fail. An emitted "likely claim" would anchor the labeller onto the very rule being
    measured, and the measurement would come back agreeing with itself whatever
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


class TestATableCellIsJudgeableOnItsOwn:
    """The one place the sentence-as-context rule leaves a labeller with nothing.

    In prose the context is a whole sentence, so `12` arrives inside "across 12 sites"
    and reads for itself. Inside a table the context *is* the cell, so the row says
    `0.840` and nothing else — unjudgeable without opening the paper, which is the one
    thing this file exists to avoid. `Model | AUC | 0.840` is judgeable; `0.840` is not.

    The two columns are derived here rather than added to `Candidate`: its `context` is
    verbatim paper text, and the record shape freezes the moment labels exist against
    it, so only what must be frozen is.
    """

    def test_a_cell_carries_its_column_header_and_row_label(self) -> None:
        by_text = {row["text"]: row for row in rows(emit(TABLE))}
        assert by_text["0.840"]["column_header"] == "AUC"
        assert by_text["0.840"]["row_label"] == "Ours"
        assert by_text["0.812"]["row_label"] == "Baseline"
        assert by_text["0.001"]["column_header"] == "p"

    def test_a_prose_candidate_has_neither(self) -> None:
        # `null`, not `""`: there is no header cell, which is a different fact from a
        # header cell that is empty. The distinction is the one `optional_sort_key`
        # makes a point of keeping elsewhere in this package.
        for row in rows(emit(ADVERSARIAL)):
            assert row["column_header"] is None
            assert row["row_label"] is None

    def test_an_empty_header_cell_stays_empty_rather_than_absent(self) -> None:
        by_text = {row["text"]: row for row in rows(emit(BLANK_HEADER))}
        assert by_text["0.840"]["column_header"] == ""
        assert by_text["0.840"]["row_label"] == "Ours"

    def test_a_cell_in_a_column_the_header_never_declared_has_none(self) -> None:
        # A row with more cells than its header: the parser records what the author
        # wrote, so there is genuinely no header cell above this number.
        by_text = {row["text"]: row for row in rows(emit(RAGGED))}
        assert by_text["0.001"]["column_header"] is None
        assert by_text["0.001"]["row_label"] == "Ours"

    def test_a_number_in_the_header_row_is_its_own_header(self) -> None:
        # Deliberate, and pinned so it is not mistaken for a bug: the rule is "the
        # row-0 cell of this column", and for a row-0 cell that is itself. Special
        # casing it would be a judgement about what a header means.
        by_text = {row["text"]: row for row in rows(emit(NUMERIC_HEADER))}
        assert by_text["2019"]["column_header"] == "2019"
        assert by_text["2019"]["row_label"] == "2019"
        assert by_text["12"]["column_header"] == "2019"
        assert by_text["12"]["row_label"] == "12"

    def test_the_table_columns_do_not_disturb_the_context_halves(self) -> None:
        for row in rows(emit(TABLE)):
            assert row["context_before"] + row["text"] + row["context_after"]

    def test_a_candidate_claiming_a_cell_it_is_not_in_is_refused(self) -> None:
        # The section hint and the cell lookup must agree. If they ever disagree, the
        # emitter is placing numbers in the wrong table columns, and a labeller would
        # be reading a header from a row the number is not in.
        prose = extract_candidates(ADVERSARIAL)[0]
        mislabelled = Candidate(
            text=prose.text,
            span=prose.span,
            context=prose.context,
            section_hint="table",
        )
        with pytest.raises(LabellingError, match="not in a table cell"):
            emit_labelling_file(
                [mislabelled], paper=ADVERSARIAL, document=DOCUMENT
            )

    def test_a_candidate_inside_a_cell_that_is_not_marked_as_one_is_refused(
        self,
    ) -> None:
        # The other direction of the same disagreement: a cell candidate that lost its
        # hint would silently emit a row with no header, and the labeller would see
        # the bare `0.840` this class exists to prevent.
        cell = next(
            candidate
            for candidate in extract_candidates(TABLE)
            if candidate.section_hint == "table"
        )
        demoted = Candidate(
            text=cell.text,
            span=cell.span,
            context=cell.context,
            section_hint="other",
        )
        with pytest.raises(LabellingError, match="is not marked as"):
            emit_labelling_file([demoted], paper=TABLE, document=DOCUMENT)

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
            "column_header",
            "row_label",
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

    def test_a_paper_that_is_not_text_is_refused(self) -> None:
        # Both directions need the paper itself: bytes would be text nobody normalized,
        # and a path would be a file read this package never does.
        with pytest.raises(TypeError, match="paper"):
            emit_labelling_file(
                extract_candidates(PAPER),
                paper=PAPER.encode("utf-8"),  # type: ignore[arg-type]
                document=DOCUMENT,
            )

    def test_an_empty_document_name_is_refused(self) -> None:
        with pytest.raises(ValueError, match="document"):
            emit(PAPER, document="")


class TestTheLoaderFailsLoudlyAndSpecifically:
    """Every rejection names the line, the row and the repair.

    A labelling file is filled in by hand, so every one of these is a thing that will
    actually happen. A loader that shrugged — skipping the unlabelled row, fixing
    the typo, ignoring the id it did not recognise — would silently shrink or corrupt
    the blind set the rule is scored against, and the score would still look fine.
    """

    def _candidates(self) -> tuple[Candidate, ...]:
        return extract_candidates(PAPER)

    def _load(self, data: bytes) -> tuple[LabelledCandidate, ...]:
        """The one good call, so each test below differs only in what it breaks."""
        return load_labels(
            data, candidates=self._candidates(), paper=PAPER, document=DOCUMENT
        )

    def test_an_unknown_id_is_rejected(self) -> None:
        data = rewrite(emit(PAPER), lambda row: {**row, "label": LABEL_CLAIM})
        broken = data.replace(
            rows(data)[0]["id"].encode("ascii"), b"0000000000000000"
        )
        with pytest.raises(LabellingError, match="unknown row id"):
            self._load(broken)

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
            self._load(one_short)

    def test_a_row_with_no_label_field_at_all_is_rejected(self) -> None:
        stripped = rewrite(
            emit(PAPER),
            lambda row: {k: v for k, v in row.items() if k != "label"},
        )
        with pytest.raises(LabellingError, match="missing field"):
            self._load(stripped)

    def test_an_unparseable_label_value_is_rejected(self) -> None:
        data = rewrite(emit(PAPER), lambda row: {**row, "label": "probably"})
        with pytest.raises(LabellingError, match="unparseable label"):
            self._load(data)

    def test_a_label_of_the_wrong_type_is_rejected(self) -> None:
        data = rewrite(emit(PAPER), lambda row: {**row, "label": True})
        with pytest.raises(LabellingError, match="unparseable label"):
            self._load(data)

    def test_a_duplicated_row_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        doubled = data + lines(data)[1].encode("utf-8") + b"\n"
        with pytest.raises(LabellingError, match="duplicate row id"):
            self._load(doubled)

    def test_a_file_missing_a_candidate_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        kept = [lines(data)[0], *lines(data)[2:]]
        short = ("\n".join(kept) + "\n").encode("utf-8")
        with pytest.raises(LabellingError, match="does not label every candidate"):
            self._load(short)

    def test_a_file_emitted_from_another_paper_is_rejected(self) -> None:
        other = fill(emit(ADVERSARIAL))
        with pytest.raises(LabellingError, match="unknown row id"):
            self._load(other)

    def test_a_file_emitted_under_another_document_name_is_rejected(self) -> None:
        elsewhere = fill(emit(PAPER, document="fixtures/papers/other.md"))
        with pytest.raises(LabellingError, match="unknown row id"):
            self._load(elsewhere)

    def test_an_edited_context_is_rejected(self) -> None:
        # Only the label column may be edited. A context quietly reworded in the
        # labelling file would mean the labeller judged text the paper does not say.
        data = fill(emit(PAPER))
        tampered = rewrite(
            data,
            lambda row: {**row, "context_after": row["context_after"] + " (sic)"},
        )
        with pytest.raises(LabellingError, match="no longer matches"):
            self._load(tampered)

    def test_an_edited_column_header_is_rejected(self) -> None:
        # Derived rather than carried on the candidate, and checked all the same: a
        # header quietly reworded means the labeller judged a number under a column
        # the paper does not have.
        data = fill(emit(TABLE))
        tampered = rewrite(data, lambda row: {**row, "column_header": "AUROC"})
        with pytest.raises(LabellingError, match="no longer matches"):
            load_labels(
                tampered,
                candidates=extract_candidates(TABLE),
                paper=TABLE,
                document=DOCUMENT,
            )

    def test_an_edited_row_label_is_rejected(self) -> None:
        data = fill(emit(TABLE))
        tampered = rewrite(data, lambda row: {**row, "row_label": "Theirs"})
        with pytest.raises(LabellingError, match="no longer matches"):
            load_labels(
                tampered,
                candidates=extract_candidates(TABLE),
                paper=TABLE,
                document=DOCUMENT,
            )

    def test_a_table_file_round_trips(self) -> None:
        candidates = extract_candidates(TABLE)
        loaded = load_labels(
            fill(emit(TABLE)),
            candidates=candidates,
            paper=TABLE,
            document=DOCUMENT,
        )
        assert [entry.candidate for entry in loaded] == list(candidates)

    def test_an_edited_section_hint_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        tampered = rewrite(data, lambda row: {**row, "section": "results"})
        with pytest.raises(LabellingError, match="no longer matches"):
            self._load(tampered)

    def test_an_unexpected_field_is_rejected(self) -> None:
        # Including the obvious one: a column of predictions helpfully added next to
        # the labels.
        data = rewrite(
            fill(emit(PAPER)), lambda row: {**row, "predicted": LABEL_CLAIM}
        )
        with pytest.raises(LabellingError, match="unexpected field"):
            self._load(data)

    def test_a_line_that_is_not_json_is_rejected_with_its_line_number(self) -> None:
        data = fill(emit(PAPER))
        broken = data + b"not json at all\n"
        with pytest.raises(LabellingError, match="line 9"):
            self._load(broken)

    def test_a_line_that_is_not_an_object_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        broken = data + b"[1, 2, 3]\n"
        with pytest.raises(LabellingError, match="JSON object"):
            self._load(broken)

    def test_a_file_without_the_header_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        headless = ("\n".join(lines(data)[1:]) + "\n").encode("utf-8")
        with pytest.raises(LabellingError, match="labelling file"):
            self._load(headless)

    def test_a_header_from_a_future_format_is_rejected(self) -> None:
        data = fill(emit(PAPER))
        future = data.replace(
            LABELLING_FORMAT.encode("ascii"), b"plumb.labelling.v99"
        )
        with pytest.raises(LabellingError, match="plumb.labelling.v1"):
            self._load(future)

    def test_an_empty_file_is_rejected(self) -> None:
        with pytest.raises(LabellingError, match="labelling file"):
            self._load(b"")

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
