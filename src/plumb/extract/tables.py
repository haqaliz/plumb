"""Markdown pipe tables, parsed into cells that are located precisely enough to cite.

A paper's headline numbers live in its tables as often as in its prose, and a table row
is the wrong unit to cite: `| AUC | 0.87 | 95% CI [0.81, 0.93] |` contains three values
and one of them is the claim. So the unit here is the **cell**, and the contract is one
sentence long:

> `normalize_text(raw)[cell.span.start:cell.span.end] == cell.text`, always.

Not the row, not the row with the padding trimmed off, not an approximation that
happens to be right when the columns are narrow. A span that resolved to its row would
still *look* correct in a report — it quotes text the paper really contains — which is
exactly why it is pinned by a test on every cell rather than left to inspection.

Three consequences of that contract, each of which looks like a detail and is not:

- **Padding is excluded.** `| AUC    |` is the cell `AUC`; the alignment spaces are
  typography and a citation that included them would point at whitespace.
- **An empty cell is a cell.** It keeps its row and column and gets a zero-width span
  (`CharSpan` permits `start == end`, which addresses a position rather than a
  quotation). Dropping it would renumber every column after it in that row.
- **Escaped pipes stay escaped.** `a \\| b` is kept verbatim, backslash and all,
  because unescaping it to `a | b` would produce a `text` that its own span no longer
  reproduces. Un-escaping for display is a consumer's decision, not this module's.

**What counts as a table** is GitHub-Flavored Markdown's rule, not a looser guess: a
header row, then a delimiter row (`|---|:--:|`) with *the same number of cells*, then
contiguous rows until a blank line or a line with no unescaped pipe. Every one of
those rows needs an unescaped pipe, the header included — otherwise `Metric\\n------`,
which is a setext heading, would read as a one-column table whose title is its only
cell. The delimiter row
is structure and yields no cells — if it produced any, every table in the corpus would
donate a row of hyphens and colons to the candidate pool. Being strict costs little:
a malformed table's numbers are still found as prose by `candidates.py`, so the only
thing lost is the cell context, whereas a table invented out of a line that merely
contains a pipe would attach cell citations to columns the author never wrote.

Known limits, stated rather than discovered later: a pipe table inside a fenced code
block is parsed like any other (fence tracking is not implemented), and a data row may
have more or fewer cells than its header — GFM would pad or truncate it, and this
parser records what is actually written instead, since a padded cell has no span.

Out of scope, deliberately: whether any cell is a claim. This module emits no verdicts.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from plumb.extract.location import CharSpan, normalize_text

__all__ = [
    "CaptionedCell",
    "CaptionedTable",
    "Table",
    "TableCell",
    "parse_captioned_tables",
    "parse_tables",
]


#: One cell of a delimiter row: hyphens, with an optional alignment colon on either
#: side. At least one hyphen is required, which is what keeps `| : |` from reading as
#: structure.
_ALIGNMENT_CELL = re.compile(r":?-+:?")

#: Only spaces and tabs are trimmed from a cell. A newline cannot occur inside one (a
#: row is a line), and trimming other Unicode whitespace would move a span off text the
#: author may have written on purpose.
_PADDING = " \t"


@dataclass(frozen=True, slots=True)
class TableCell:
    """One cell, its text, and where that text is in the normalized paper.

    `row` counts from 0 at the header; the delimiter row consumes no index, so the
    first data row is row 1. `column` counts from 0 at the left, counting the cells the
    author actually wrote — an empty cell included.

    `frozen=True, slots=True` for the same reason every record in this package carries
    them: no mutation after the fact, and no `__dict__` for a later stage to attach a
    confidence score to (`claim.py`, `CLAUDE.md` #1).
    """

    text: str
    span: CharSpan
    row: int
    column: int

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError(
                f"TableCell.text must be a string, got {type(self.text).__name__}: "
                f"{self.text!r}"
            )
        if not isinstance(self.span, CharSpan):
            raise TypeError(
                "TableCell.span must be a CharSpan into the normalized text, got "
                f"{type(self.span).__name__}: {self.span!r}"
            )
        for name in ("row", "column"):
            value = getattr(self, name)
            # `bool` is an `int` subclass; True as a row index is a bug, not a number.
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(
                    f"TableCell.{name} must be an int index, got "
                    f"{type(value).__name__}: {value!r}"
                )
            if value < 0:
                raise ValueError(
                    f"TableCell.{name} must be non-negative, got {value}"
                )


@dataclass(frozen=True, slots=True)
class Table:
    """One pipe table: its cells in document order, and the span of the whole table.

    `span` runs from the first character of the header line to the last character of
    the final row, excluding the trailing newline. It exists so a later stage can ask
    "is this offset inside a table?" without re-deriving the table's extent from its
    cells — the gaps between cells (pipes, padding, the delimiter row) belong to the
    table too, and a union of cell spans would leave them out.
    """

    cells: tuple[TableCell, ...]
    span: CharSpan

    def __post_init__(self) -> None:
        if not isinstance(self.cells, tuple):
            raise TypeError(
                f"Table.cells must be a tuple, got {type(self.cells).__name__}: "
                f"{self.cells!r}"
            )
        for cell in self.cells:
            if not isinstance(cell, TableCell):
                raise TypeError(
                    "Table.cells must contain TableCell records, got "
                    f"{type(cell).__name__}: {cell!r}"
                )
        if not isinstance(self.span, CharSpan):
            raise TypeError(
                "Table.span must be a CharSpan into the normalized text, got "
                f"{type(self.span).__name__}: {self.span!r}"
            )


def _line_regions(text: str) -> tuple[tuple[int, int], ...]:
    """`(start, end)` of every line, `end` excluding the newline.

    Built by scanning rather than by `splitlines()`, because the offsets are the point:
    `splitlines()` also breaks on `\\v`, `\\f`, `\\x85` and `\\u2028`, and a line
    boundary this parser saw but `normalize_text` did not would shift every span after
    it. The only separator here is `\\n`, which is the only one normalization leaves.
    """
    regions: list[tuple[int, int]] = []
    start = 0
    while True:
        newline = text.find("\n", start)
        if newline < 0:
            regions.append((start, len(text)))
            return tuple(regions)
        regions.append((start, newline))
        start = newline + 1


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    """Narrow `[start, end)` past leading and trailing spaces and tabs."""
    while start < end and text[start] in _PADDING:
        start += 1
    while end > start and text[end - 1] in _PADDING:
        end -= 1
    return start, end


def _row_fields(text: str, start: int, end: int) -> tuple[tuple[int, int], ...] | None:
    """Split one line into field regions, or `None` if it is not a table row.

    `None` means "no unescaped pipe here", which is how a table's extent is decided:
    the blank line after a table has none, and neither does the prose after it.

    A backslash escapes whatever follows it, so `\\|` is text and `\\\\|` is a literal
    backslash followed by a real delimiter. That is a two-character skip, not a
    `pipe not preceded by a backslash` test — the latter gets `\\\\|` wrong, and gets
    it wrong silently, by fusing two cells into one.

    The outer pipes of `| a | b |` are delimiters rather than cell boundaries: they
    would otherwise yield an empty cell at each end of every row, which is
    indistinguishable from the empty cells an author really wrote.
    """
    start, end = _trim(text, start, end)
    fields: list[tuple[int, int]] = []
    delimiters: list[int] = []
    field_start = start
    cursor = start
    while cursor < end:
        character = text[cursor]
        if character == "\\":
            cursor += 2
            continue
        if character == "|":
            delimiters.append(cursor)
            fields.append((field_start, cursor))
            field_start = cursor + 1
        cursor += 1
    fields.append((field_start, end))

    if not delimiters:
        return None
    first = 1 if delimiters[0] == start else 0
    last = len(fields) - 1 if delimiters[-1] == end - 1 else len(fields)
    return tuple(fields[first:last])


def _cell(text: str, region: tuple[int, int], row: int, column: int) -> TableCell:
    """One field region, with its padding trimmed off the *span* as well as the text."""
    start, end = _trim(text, *region)
    return TableCell(text=text[start:end], span=CharSpan(start, end), row=row, column=column)


def _is_alignment_row(
    text: str, fields: tuple[tuple[int, int], ...], columns: int
) -> bool:
    """Is this the `|---|:--:|` row that turns a pair of lines into a table?

    The column count must match the header's, which is GFM's rule. Without it a single
    `|---|` under a three-column header would be accepted and the table's columns would
    be whatever the parser felt like.
    """
    if len(fields) != columns:
        return False
    for start, end in fields:
        lead, tail = _trim(text, start, end)
        if _ALIGNMENT_CELL.fullmatch(text[lead:tail]) is None:
            return False
    return True


def parse_tables(raw: str) -> tuple[Table, ...]:
    """Every pipe table in `raw`, in document order, as located cells.

    `raw` is normalized on the way in and **every offset returned indexes that
    normalized text**, not the string passed in. `normalize_text` is idempotent, so
    passing already-normalized text is the same call; passing a CRLF checkout of the
    same paper yields the same spans, which is what keeps a citation pointing at the
    same characters the paper hash covers (`hashing.py`).

    Never raises on malformed input: a document with no tables is `()`. A parser that
    threw partway through a paper would lose the rest of the paper.
    """
    text = normalize_text(raw)
    lines = _line_regions(text)
    tables: list[Table] = []

    index = 0
    while index + 1 < len(lines):
        header = _row_fields(text, *lines[index])
        if not header:
            index += 1
            continue
        alignment = _row_fields(text, *lines[index + 1])
        if alignment is None or not _is_alignment_row(text, alignment, len(header)):
            index += 1
            continue

        cells = [
            _cell(text, region, 0, column) for column, region in enumerate(header)
        ]
        last_line = index + 1
        row = 1
        cursor = index + 2
        while cursor < len(lines):
            fields = _row_fields(text, *lines[cursor])
            if not fields:
                break
            cells.extend(
                _cell(text, region, row, column)
                for column, region in enumerate(fields)
            )
            last_line = cursor
            row += 1
            cursor += 1

        tables.append(
            Table(
                cells=tuple(cells),
                span=CharSpan(lines[index][0], lines[last_line][1]),
            )
        )
        index = cursor

    return tuple(tables)


# --- the second form: caption-led whitespace tables ------------------------------------
#
# A PDF text layer turns a typeset table into lines of words and numbers under its
# caption, with no pipes (AgroDesign: `Treatment 3 363.333 145.333<0.001`). Read as
# prose, every cell of a row is named by the row label alone, and distinct cells — the
# MS and the F of one row — become one claim id. So these tables are recognised too, but
# only in a strict shape, because a table invented out of prose would attach names the
# author never wrote:
#
# - a whole line `Table N:` (or `Table N.`) — the caption;
# - optionally one header line: not a row, not an ATX heading, no purely numeric token,
#   at least two tokens, and exactly one token per cell of the first row plus one for
#   the label column — otherwise the caption opens no table (a wrapped caption line
#   reads just like a header of words);
# - then at least two consecutive rows. A row's cells are the longest run of cell tokens
#   at its end — a number, a dash, or a glued `number<number` (two cells: the PDF lost
#   the space); its label is the rest, which must contain a letter. The first line that
#   is not a row ends the table.
#
# Column names come from the header for every row it fits; a ragged row gets
# `column k`. A row label that ends in a number
# (`Model 2 0.87`) reads the number as a cell — undecidable from the text; the header
# check then falls back to ordinals rather than misnaming. Pipe tables are never
# re-read here, and their cells stay unnamed.

_CAPTION = re.compile(r"Table (\d+)[:.](?:\s.*)?")
_ATX = re.compile(r"#{1,6}(?:[ \t]|$)")
_NUMERIC = r"[+-]?(?:\d+\.\d+|\d+|\.\d+)"
_CELL_TOKEN = re.compile(rf"{_NUMERIC}|[–—-]|{_NUMERIC}[<>]{_NUMERIC}")
_GLUED = re.compile(rf"({_NUMERIC})([<>]{_NUMERIC})")
_DASH = re.compile(r"[–—-]")
_TOKEN = re.compile(r"\S+")
_NUMBER_ONLY = re.compile(_NUMERIC)


@dataclass(frozen=True, slots=True)
class CaptionedCell:
    """A cell of a caption-led whitespace table, and the names the paper wrote for it.

    `header` is `Table {n} {row label} {column name}` — words read off the caption
    number, the row and the header line, never inferred. It is what distinguishes the MS
    of a row from its F once both become claims.
    """

    cell: TableCell
    header: str


@dataclass(frozen=True, slots=True)
class CaptionedTable:
    """One caption-led whitespace table: its extent and its named cells."""

    table: Table
    cells: tuple[CaptionedCell, ...]

    def __iter__(self):
        return iter(self.cells)


def _row(text: str, start: int, end: int) -> tuple[str, list[tuple[int, int] | None]] | None:
    """A row's label and its cell regions (`None` for a dash), or `None` if not a row."""
    tokens = [(m.start() + start, m.end() + start) for m in _TOKEN.finditer(text[start:end])]
    split = len(tokens)
    while split > 0 and _CELL_TOKEN.fullmatch(text[tokens[split - 1][0]:tokens[split - 1][1]]):
        split -= 1
    if split == 0 or split == len(tokens):
        return None
    label = text[tokens[0][0]:tokens[split - 1][1]]
    if not any(char.isalpha() for char in label):
        return None
    cells: list[tuple[int, int] | None] = []
    for token_start, token_end in tokens[split:]:
        token = text[token_start:token_end]
        glued = _GLUED.fullmatch(token)
        if glued is not None:
            cells.append((token_start + glued.start(1), token_start + glued.end(1)))
            cells.append((token_start + glued.start(2), token_start + glued.end(2)))
        elif _DASH.fullmatch(token):
            cells.append(None)
        else:
            cells.append((token_start, token_end))
    return label, cells


def _header(text: str, start: int, end: int) -> list[str] | None:
    line = text[start:end]
    tokens = line.split()
    if (
        len(tokens) < 2
        or _ATX.match(line)
        or _row(text, start, end) is not None
        or any(_NUMBER_ONLY.fullmatch(token) for token in tokens)
    ):
        return None
    return tokens


def parse_captioned_tables(raw: str) -> tuple[CaptionedTable, ...]:
    """Every caption-led whitespace table in the paper, in document order.

    Offsets index `normalize_text(raw)`, like `parse_tables`. Lines inside a pipe table
    are never considered: a pipe is not a cell token, so no such line is a row.
    """
    text = normalize_text(raw)
    lines = _line_regions(text)
    tables: list[CaptionedTable] = []
    index = 0
    while index < len(lines):
        start, end = lines[index]
        caption = _CAPTION.fullmatch(text[start:end])
        if caption is None:
            index += 1
            continue
        cursor = index + 1
        header = None
        if cursor + 1 < len(lines):
            header = _header(text, *lines[cursor])
            first_row = _row(text, *lines[cursor + 1])
            if header is not None and (
                first_row is None or len(header) != len(first_row[1]) + 1
            ):
                # Words that do not name the first row's columns are not a header —
                # a wrapped caption reads just like one.
                index += 1
                continue
            if header is not None:
                cursor += 1
        rows: list[tuple[int, str, list[tuple[int, int] | None]]] = []
        while cursor < len(lines):
            row = _row(text, *lines[cursor])
            if row is None:
                break
            rows.append((cursor, *row))
            cursor += 1
        if len(rows) < 2:
            index += 1
            continue
        number = caption.group(1)
        named: list[CaptionedCell] = []
        for row_number, (_, label, regions) in enumerate(rows, start=1):
            fits = header is not None and len(header) == len(regions) + 1
            for column, region in enumerate(regions, start=1):
                if region is None:
                    continue
                name = header[column] if fits else f"column {column}"
                named.append(
                    CaptionedCell(
                        cell=_cell(text, region, row_number, column),
                        header=f"Table {number} {label} {name}",
                    )
                )
        first = lines[index + 1][0]
        last = lines[rows[-1][0]][1]
        tables.append(
            CaptionedTable(
                table=Table(
                    cells=tuple(c.cell for c in named), span=CharSpan(first, last)
                ),
                cells=tuple(named),
            )
        )
        index = cursor
    return tuple(tables)
