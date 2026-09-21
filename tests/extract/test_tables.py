"""Tests for Markdown pipe-table parsing.

The load-bearing contract: **a cell's `CharSpan` round-trips to the cell's own text,
not to its row's.** A claim cited to a table has to point at the number, not at the
line the number happened to sit on, so every test here that touches a span checks it
by slicing `normalize_text(document)` and comparing against the cell text.

Nothing in this module decides whether a cell is a claim. That is a later stage's job,
and this file asserts no verdicts of any kind.
"""

from dataclasses import FrozenInstanceError

import pytest

from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.tables import Table, TableCell, parse_tables

# A table with a leading and trailing pipe, an alignment row carrying colons, an empty
# cell, and numbers of two shapes. The prose around it is there so that offsets are not
# accidentally correct for a document that begins at the table.
DOCUMENT = """\
# Results

We report the following.

| Metric | Value | Units |
|--------|------:|:-----:|
| AUC    | 0.87  |       |
| Rate   | 12.5  | %     |

Discussion follows.
"""

# The same table written without outer pipes, which is legal Markdown.
BARE = """\
Metric | Value
------ | -----
AUC    | 0.87
"""


def cells_of(document: str) -> tuple[TableCell, ...]:
    """Every cell of every table in `document`, in the order the parser emits them."""
    return tuple(cell for table in parse_tables(document) for cell in table.cells)


def texts_of(document: str) -> tuple[str, ...]:
    return tuple(cell.text for cell in cells_of(document))


class TestTheCellSpanIsTheCellAndNotTheRow:
    """The whole point of the module, asserted first."""

    @pytest.mark.parametrize("document", [DOCUMENT, BARE])
    def test_every_cell_span_round_trips_to_its_own_text(self, document: str) -> None:
        normalized = normalize_text(document)

        for cell in cells_of(document):
            assert normalized[cell.span.start : cell.span.end] == cell.text

    def test_a_numeric_cell_reproduces_exactly_and_excludes_its_neighbours(
        self,
    ) -> None:
        normalized = normalize_text(DOCUMENT)
        auc = next(cell for cell in cells_of(DOCUMENT) if cell.text == "0.87")

        # The number, and only the number: not the row, not the padding, not the
        # metric name sharing the line.
        assert normalized[auc.span.start : auc.span.end] == "0.87"
        assert auc.span.end - auc.span.start == len("0.87")
        row_start = normalized.rindex("\n", 0, auc.span.start) + 1
        row_end = normalized.index("\n", auc.span.end)
        assert row_end - row_start > auc.span.end - auc.span.start
        assert "AUC" not in normalized[auc.span.start : auc.span.end]

    def test_padding_is_not_part_of_the_cell(self) -> None:
        # `| AUC    |` is one cell whose text is `AUC`. Keeping the padding would make
        # every citation point at whitespace the author used for alignment.
        auc = next(cell for cell in cells_of(DOCUMENT) if cell.text == "AUC")
        normalized = normalize_text(DOCUMENT)

        assert normalized[auc.span.start : auc.span.end] == "AUC"
        assert not auc.text.startswith(" ")
        assert not auc.text.endswith(" ")


class TestTableShape:
    def test_a_table_with_outer_pipes_yields_every_cell(self) -> None:
        assert texts_of(DOCUMENT) == (
            "Metric",
            "Value",
            "Units",
            "AUC",
            "0.87",
            "",
            "Rate",
            "12.5",
            "%",
        )

    def test_a_table_without_outer_pipes_parses(self) -> None:
        assert texts_of(BARE) == ("Metric", "Value", "AUC", "0.87")

    def test_the_alignment_row_yields_no_cells(self) -> None:
        # `|--------|------:|:-----:|` is structure. If it produced cells, a paper
        # would gain three claim candidates made of hyphens and colons.
        for text in texts_of(DOCUMENT):
            assert "-" not in text
            assert ":" not in text
        assert len(cells_of(DOCUMENT)) == 9

    def test_an_empty_cell_is_preserved_rather_than_skipped(self) -> None:
        empty = [cell for cell in cells_of(DOCUMENT) if cell.text == ""]

        assert len(empty) == 1
        # Position-bearing: it is the third column of the first data row, and dropping
        # it would shift every later column of that row by one.
        assert (empty[0].row, empty[0].column) == (1, 2)
        assert empty[0].span.start == empty[0].span.end

    def test_rows_and_columns_are_numbered_from_the_header(self) -> None:
        by_text = {cell.text: (cell.row, cell.column) for cell in cells_of(DOCUMENT)}

        assert by_text["Metric"] == (0, 0)
        assert by_text["Units"] == (0, 2)
        # The alignment row consumes no row index: the first data row is row 1.
        assert by_text["AUC"] == (1, 0)
        assert by_text["0.87"] == (1, 1)
        assert by_text["Rate"] == (2, 0)

    def test_the_table_span_covers_the_table_and_nothing_around_it(self) -> None:
        normalized = normalize_text(DOCUMENT)
        (table,) = parse_tables(DOCUMENT)
        covered = normalized[table.span.start : table.span.end]

        assert covered.startswith("| Metric")
        assert covered.endswith("| %     |")
        assert "Discussion" not in covered
        assert "We report" not in covered

    def test_two_tables_in_one_document_stay_separate(self) -> None:
        document = DOCUMENT + "\n" + BARE
        tables = parse_tables(document)

        assert len(tables) == 2
        assert len(tables[0].cells) == 9
        assert len(tables[1].cells) == 4
        assert tables[0].span.end < tables[1].span.start


class TestEscapedPipes:
    ESCAPED = """\
| Note    | Value |
|---------|-------|
| a \\| b  | 0.5   |
"""

    def test_an_escaped_pipe_does_not_split_a_cell(self) -> None:
        assert texts_of(self.ESCAPED) == ("Note", "Value", "a \\| b", "0.5")

    def test_the_escaped_cell_still_round_trips(self) -> None:
        # Verbatim, backslash included: unescaping here would break the round-trip
        # that every citation depends on.
        normalized = normalize_text(self.ESCAPED)
        cell = next(c for c in cells_of(self.ESCAPED) if c.text == "a \\| b")

        assert normalized[cell.span.start : cell.span.end] == "a \\| b"

    def test_a_backslash_before_a_backslash_does_not_escape_the_pipe(self) -> None:
        # `\\|` is a literal backslash followed by a real delimiter.
        document = "| a | b |\n|---|---|\n| x\\\\ | y |\n"

        assert texts_of(document) == ("a", "b", "x\\\\", "y")


class TestWhatIsNotATable:
    def test_prose_containing_a_pipe_is_not_a_table(self) -> None:
        assert parse_tables("The set A | B was used.\nAnd nothing else.\n") == ()

    def test_a_header_without_an_alignment_row_is_not_a_table(self) -> None:
        assert parse_tables("| a | b |\n| c | d |\n") == ()

    def test_an_alignment_row_of_the_wrong_width_is_not_a_table(self) -> None:
        # GFM requires the delimiter row to match the header's column count. Parsing
        # it anyway would invent a column, and a cell span pointing into a column the
        # author never wrote is worse than no table at all — the numbers are still
        # found as prose.
        assert parse_tables("| a | b |\n|---|\n| c | d |\n") == ()

    def test_a_setext_heading_is_not_a_one_column_table(self) -> None:
        # `Metric\n------` is a level-2 heading in Markdown, and every heading in a
        # paper written that way would otherwise become a one-column table whose
        # title is its only cell. A row needs an unescaped pipe to be a row.
        assert parse_tables("Metric\n------\n0.87\n") == ()

    def test_a_table_ends_at_a_blank_line(self) -> None:
        document = "| a |\n|---|\n| 1 |\n\n| loose | text\n"

        assert texts_of(document) == ("a", "1")


class TestOffsetsAreMeasuredInNormalizedText:
    def test_a_crlf_document_yields_the_same_spans_as_its_lf_twin(self) -> None:
        # The offsets index `normalize_text(raw)`, so a Windows checkout and a macOS
        # one must produce identical spans — the same rule `hash_paper` follows.
        crlf = DOCUMENT.replace("\n", "\r\n")

        assert cells_of(crlf) == cells_of(DOCUMENT)
        normalized = normalize_text(crlf)
        for cell in cells_of(crlf):
            assert normalized[cell.span.start : cell.span.end] == cell.text

    def test_offsets_are_character_offsets_not_byte_offsets(self) -> None:
        document = "| µ-cohort | α |\n|---|---|\n| 0.87 | 12 |\n"
        normalized = normalize_text(document)
        cell = next(c for c in cells_of(document) if c.text == "0.87")
        as_bytes = normalized.encode("utf-8")

        assert len(as_bytes) > len(normalized)
        assert as_bytes[cell.span.start : cell.span.end].decode("utf-8", "replace") != (
            "0.87"
        )
        assert normalized[cell.span.start : cell.span.end] == "0.87"


class TestDeterminism:
    def test_the_same_document_parses_identically_twice(self) -> None:
        assert parse_tables(DOCUMENT) == parse_tables(DOCUMENT)

    def test_cells_are_emitted_in_document_order(self) -> None:
        spans = [cell.span.start for cell in cells_of(DOCUMENT)]

        assert spans == sorted(spans)


class TestTheRecordsAreSealed:
    def test_a_cell_is_frozen(self) -> None:
        cell = cells_of(DOCUMENT)[0]

        with pytest.raises(FrozenInstanceError):
            cell.text = "other"  # type: ignore[misc]

    def test_a_cell_rejects_an_extra_attribute(self) -> None:
        # `slots=True`: no `__dict__` for a later stage to hang a confidence score on.
        cell = cells_of(DOCUMENT)[0]

        with pytest.raises(AttributeError):
            object.__setattr__(cell, "confidence", "0.9")

    def test_a_cell_requires_a_char_span(self) -> None:
        with pytest.raises(TypeError):
            TableCell(text="x", span="0:1", row=0, column=0)  # type: ignore[arg-type]

    def test_a_table_requires_cells_to_be_cells(self) -> None:
        with pytest.raises(TypeError):
            Table(cells=("x",), span=CharSpan(0, 1))  # type: ignore[arg-type]
