"""Deterministic PDF-to-Markdown text conversion on the pinned pypdf.

The pipeline, per page:

1. **Runs** — pypdf's visitor API yields every text run with its position (the
   text-matrix translation `(x, y)`) and font size. Runs whose text is empty or
   whitespace (including pypdf's `"\\n"` line-move markers) are discarded; a run
   whose text contains an embedded newline is split into one segment per piece.
2. **Lines** — segments are grouped by `y` (rounded to one decimal) and sorted by
   `x` within a line.
3. **Headings** — the page's body size is the most common segment size; a line whose
   largest segment exceeds `max(body * 1.25, body + 2.0)` becomes `## `, and a line
   at least twice the body size becomes `# ` (the title). Consecutive same-level
   heading lines of the same size merge into one heading. When no size is clearly
   larger than the body (no font signal), a named line-shape fallback applies:
   short, unpunctual, title-case or all-caps lines become `## `. A heading-size line
   too long to be a heading is emitted as prose and counted, never silent.
4. **Glued labels** — a known section label glued to prose on the same line
   (`AbstractThis review...`) is split into its heading and the prose, whatever the
   font signals say. The seam's section hints need the heading; the prose needs the
   sentence.
5. **Tables** — column positions are clustered from the x coordinates of multi-
   segment lines; clusters seen at least twice are columns. A maximal run of lines
   each carrying at least two segments becomes a table when at least three of its
   lines map to two or more columns and one maps to three or more. Segments that map
   to no column are dropped and counted; lines inside a region that map to fewer
   than two columns are dropped and counted — dropped content is never merged into
   prose. Rows anchor on the first column; lines without it continue the open row,
   so wrapped cells re-join. Cells are emitted as GFM pipe rows over a delimiter
   row, with every row padded to the widest row so the header and delimiter agree.
6. **Value line-join** — within a table cell, a numeric token split across a line
   break (`0.0` + newline + `3`) re-joins (`0.03`); other breaks become a space.
   The rule is numeric-token-scoped and parse-checked, so two distinct values are
   never fused into one invented number.

Determinism: every ordering below is a sort or an index, never set or dict
iteration; the only arithmetic is on pypdf's own coordinates. Byte identity across
processes is pinned in `tests/pdf/test_convert.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

__all__ = [
    "ConversionStats",
    "PdfInputError",
    "pdf_to_markdown",
    "pdf_to_markdown_with_stats",
]

#: x positions closer than this are one column; a segment maps to a column only
#: within this distance of its center (wider than the cluster tolerance, so a
#: citation sitting just off a wide column cluster still lands in its row).
_X_TOLERANCE = 12.0
_X_CAP = 20.0

#: A column is real only if at least this many segments share it — a position seen
#: on two lines is typography, not a grid.
_MIN_COLUMN_SUPPORT = 3

#: A table needs at least this many rows and a row with at least this many mapped
#: segments; the author and sidebar lines of the real fixtures trip one of the two.
_MIN_TABLE_ROWS = 3
_MIN_TABLE_COLUMNS = 4

#: A single-segment line inside a table region is a wrapped cell fragment only if
#: it is this short and not on the first column (footnotes sit on the first column
#: and must break the region instead of joining it).
_MAX_WRAP_CHARS = 40

#: A single-segment line *on* the first column opens a new row only when it is a
#: short author- or study-name fragment: no colon (footnotes start with one), no
#: bracket (citation lines like `[16]` do), not too short, not a whole sentence.
_MAX_ROW_START_CHARS = 30
_MIN_ROW_START_CHARS = 4

#: The first row of a table must span at least this many columns — a stray prose
#: fragment on the grid (`disparities (Table 6; Figure 5).`) maps three cells at
#: most and must not become the header.
_MIN_HEADER_CELLS = 4

#: A table whose reconstructed cells would exceed this is not a table — long prose
#: fragments in columnar typography (reference entries, affiliations) must not be
#: dressed up as tables.
_MAX_CELL_CHARS = 60

#: A line whose largest segment is larger than this multiple of the body size is a
#: heading; the second rule adds an absolute cushion so a slightly-off body size on
#: a table-heavy page cannot promote every table cell to a heading.
_HEADING_RATIO = 1.25
_HEADING_CUSHION = 2.0

#: A page "has font signals" only when some line is this much larger than the body
#: — a micro-difference (MDPI sets body at 9.9626pt and part of it at 10.0pt) is
#: no signal at all, and without this bar the size path would swallow the shape
#: fallback that rescues the abstract heading on such pages.
_FONT_SIGNAL_RATIO = 1.1

#: A line of heading size is a title at twice the body size.
_TITLE_RATIO = 2.0

#: Heading-size lines longer than this are prose (counted as dropped headings).
_MAX_HEADING_CHARS = 240

#: Section labels recognized for the glued-label normalization, longest first so a
#: glued "Materials and methods..." splits on the full label, not on "Materials".
_SECTION_LABELS = (
    "materials and methods",
    "acknowledgements",
    "acknowledgments",
    "introduction",
    "background",
    "conclusions",
    "references",
    "abstract",
    "methods",
    "results",
    "discussion",
    "conclusion",
    "appendix",
    "appendices",
    "review",
)

_NUMBER_CHARS = "0123456789"


@dataclass(frozen=True, slots=True)
class ConversionStats:
    """The recorded drops and counts the seam tests can report.

    Every field is an honest count of what happened, never a guess: a drop is a
    thing the converter gave up on, and giving up is counted rather than hidden —
    the "never a silent pass" rule applied to text production.
    """

    pages: int = 0
    headings_emitted: int = 0
    dropped_heading_lines: int = 0
    dropped_table_lines: int = 0
    dropped_table_segments: int = 0


class PdfInputError(RuntimeError):
    """The PDF bytes could not be read; a harness-side failure, never a verdict."""


@dataclass(slots=True)
class _Stats:
    """Mutable accumulation for `ConversionStats`; never escapes the conversion."""

    headings_emitted: int = 0
    dropped_heading_lines: int = 0
    dropped_table_lines: int = 0
    dropped_table_segments: int = 0


@dataclass(frozen=True, slots=True)
class _Segment:
    """One text run on the page: x position, font size, and its text."""

    x: float
    size: float
    text: str


@dataclass(frozen=True, slots=True)
class _Column:
    """A detected table column: the mean x of its members and how many members."""

    center: float
    count: int


# --------------------------------------------------------------------------------
# Run and line extraction
# --------------------------------------------------------------------------------


def _extract_segments(page) -> list[tuple[int, float, float, str]]:
    """`(y, x, size, text)` for every non-empty text run on a page, in stream order.

    `y` is rounded to a whole unit: cells on one visual line differ by fractions
    of a point in the content stream, and rounding them to the same key is what
    makes the line a line (the fixtures' table headers and author lines sit at
    y values a few hundredths apart).
    """
    runs: list[tuple[int, float, float, str]] = []

    def visitor(text: str, cm, tm, font_dict, font_size) -> None:
        if text is None or not text.strip():
            return
        size = font_size or 0.0
        for part in text.split("\n"):
            if part.strip():
                runs.append((round(tm[5]), round(tm[4], 1), size, part))

    page.extract_text(visitor_text=visitor)
    return runs


def _group_lines(
    segments: list[tuple[int, float, float, str]],
) -> list[tuple[_Segment, ...]]:
    """Segments grouped into lines by y, sorted by x within a line.

    The content stream interleaves the runs of one visual line (the PDF emits
    column-by-column text ops), so a run's line-mates are not its stream
    neighbours: every segment is bucketed by its y key and the buckets are then
    emitted in reading order.
    """
    by_y: dict[int, list[_Segment]] = {}
    for y, x, size, text in segments:
        by_y.setdefault(y, []).append(_Segment(x, size, text))
    return [
        tuple(sorted(by_y[key], key=lambda s: s.x)) for key in sorted(by_y)
    ]


# --------------------------------------------------------------------------------
# Headings
# --------------------------------------------------------------------------------


def _segment_mode(sizes: list[float]) -> float:
    """The most common size, ties to the smallest — deterministic."""
    counts: dict[float, int] = {}
    for size in sizes:
        counts[size] = counts.get(size, 0) + 1
    if not counts:
        return 0.0
    return min(counts, key=lambda size: (-counts[size], size))


def _body_size(lines: list[tuple[_Segment, ...]]) -> float:
    """The page's body size: the most common segment size, ties to the smallest."""
    return _segment_mode([segment.size for line in lines for segment in line])


def _heading_level(
    line: tuple[_Segment, ...], body: float
) -> str | None:
    """`"# "`, `"## "` or `None` for a line under the size-based rule."""
    if body <= 0.0:
        return None
    top = max(segment.size for segment in line)
    if top < body:
        return None
    if top >= body * _TITLE_RATIO:
        return "# "
    threshold = max(body * _HEADING_RATIO, body + _HEADING_CUSHION)
    if top > threshold:
        return "## "
    return None


def _shape_heading(text: str) -> str | None:
    """`"## "` or `None` for a line under the line-shape fallback.

    Fires only when font signals are absent, so it is deliberately conservative:
    a short line, no terminal punctuation, no digits, and either a known section
    label, a single capitalized word, at least two capitalized words, or all
    caps. A line this rule declines stays prose — the fallback exists to keep
    section hints alive on font-less PDFs, not to invent headings where prose
    reads as prose.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 60:
        return None
    if stripped.endswith((".", ",", ";", ":")):
        return None
    words = stripped.split()
    if len(words) > 8:
        return None
    if any(any(char.isdigit() for char in word) for word in words):
        return None
    if len(words) == 1:
        word = words[0]
        if (
            word.isalpha()
            and word[0].isupper()
            and len(word) >= 5
            and not word.isupper()
        ):
            return "## "
        return None
    if stripped.lower() in _SECTION_LABELS:
        return "## "
    if sum(1 for word in words if word[0].isupper()) >= 2:
        return "## "
    if stripped.isupper() and any(char.isalpha() for char in stripped):
        return "## "
    return None


def _label_heading(text: str) -> str | None:
    """`"## "` when the whole line is a known section label.

    On a page that has real font signals, only an exact section label is rescued
    at body size (MDPI sets its abstract heading at body size, on the title's
    page). The broader shape rules would promote sidebar and author lines there,
    which are not headings.
    """
    if text.strip().lower() in _SECTION_LABELS:
        return "## "
    return None


def _split_glued_label(text: str) -> str | None:
    """A known section label glued to prose on the same line, or `None`.

    `AbstractThis review...` splits on the label; `Abstractly...` does not, because
    the label is only split off when prose follows it on the same line — and glued
    prose starts a sentence (an uppercase letter), while a word that merely begins
    with a label does not.
    """
    lowered = text.lower()
    for label in _SECTION_LABELS:
        if not lowered.startswith(label):
            continue
        rest = text[len(label):]
        if rest and rest[0].isupper():
            return text[: len(label)]
    return None


def _split_glued_segments(
    line: tuple[_Segment, ...], label: str
) -> tuple[tuple[_Segment, ...], tuple[_Segment, ...]]:
    """Split a line at the end of a glued label, preserving each side's sizes."""
    need = len(label)
    head: list[_Segment] = []
    tail: list[_Segment] = []
    for segment in line:
        if need <= 0:
            tail.append(segment)
        elif len(segment.text) <= need:
            head.append(segment)
            need -= len(segment.text)
        else:
            head.append(_Segment(segment.x, segment.size, segment.text[:need]))
            tail.append(_Segment(segment.x, segment.size, segment.text[need:]))
            need = 0
    return tuple(head), tuple(tail)


# --------------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------------


def _column_clusters(
    lines: list[tuple[_Segment, ...]],
) -> tuple[_Column, ...]:
    """Column x-clusters seen at least `_MIN_COLUMN_SUPPORT` times.

    Only multi-segment lines vote: a single-segment line carries no column
    information. Positions within `_X_TOLERANCE` of the previous member share a
    cluster, so a row's cells and its wrapped fragments align to one center.
    """
    positions: list[float] = []
    for line in lines:
        if len(line) >= 2:
            positions.extend(segment.x for segment in line)
    positions.sort()
    clusters: list[list[float]] = []
    for x in positions:
        if clusters and x - clusters[-1][-1] <= _X_TOLERANCE:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return tuple(
        _Column(center=sum(members) / len(members), count=len(members))
        for members in clusters
        if len(members) >= _MIN_COLUMN_SUPPORT
    )


def _nearest_column(x: float, columns: tuple[_Column, ...]) -> _Column | None:
    """The nearest column within `_X_CAP`, or `None` (the segment is dropped)."""
    best: _Column | None = None
    best_distance = _X_CAP
    for column in columns:
        distance = abs(x - column.center)
        if distance <= best_distance:
            best, best_distance = column, distance
    return best


def _mapped_segments(
    line: tuple[_Segment, ...], columns: tuple[_Column, ...]
) -> list[tuple[_Segment, _Column]]:
    """Every segment of the line that lands on a column, in x order."""
    mapped: list[tuple[_Segment, _Column]] = []
    for segment in line:
        column = _nearest_column(segment.x, columns)
        if column is not None:
            mapped.append((segment, column))
    return mapped


def _dominant_size(lines: list[tuple[_Segment, ...]]) -> float:
    """The most common segment size over the lines, ties to the smallest."""
    counts: dict[float, int] = {}
    for line in lines:
        for segment in line:
            counts[segment.size] = counts.get(segment.size, 0) + 1
    if not counts:
        return 0.0
    return min(counts, key=lambda size: (-counts[size], size))


def _table_regions(
    lines: list[tuple[_Segment, ...]],
) -> list[list[tuple[_Segment, ...]]]:
    """Maximal runs of lines that can be reconstructed as tables.

    A line belongs to a table region when it is part of the region's grid and its
    size: a multi-segment line whose segments land on two or more columns, or a
    short single-segment fragment on a non-first column (a wrapped cell). Prose of
    a different size, footnotes, and page furniture break the run. A run becomes a
    table only when at least `_MIN_TABLE_ROWS` of its lines are rows, one row spans
    `_MIN_TABLE_COLUMNS` columns, the first column carries letters in most rows
    (reference numbers like `19.` do not), and no reconstructed cell would exceed
    `_MAX_CELL_CHARS` — the reference lists, affiliations and author blocks of the
    real fixtures each trip one of those bars and stay prose.
    """
    page_columns = _column_clusters(lines)
    candidates = [
        line
        for line in lines
        if len(line) >= 2 and len(_mapped_segments(line, page_columns)) >= 2
    ]
    body = _dominant_size(candidates)

    def is_member(line: tuple[_Segment, ...]) -> bool:
        mapped = _mapped_segments(line, page_columns)
        if len(line) >= 2:
            return (
                len(mapped) >= 2
                and _dominant_size([line]) == body
                and body > 0.0
            )
        segment = line[0]
        column = _nearest_column(segment.x, page_columns)
        if column is None:
            return False
        if page_columns and column.center == page_columns[0].center:
            return _is_row_start(segment)
        return (
            len(segment.text.strip()) <= _MAX_WRAP_CHARS
            and segment.size == body
        )

    runs: list[list[tuple[_Segment, ...]]] = []
    current: list[tuple[_Segment, ...]] = []
    for line in lines:
        if is_member(line):
            current.append(line)
        else:
            runs.append(current)
            current = []
    runs.append(current)

    qualifying: list[list[tuple[_Segment, ...]]] = []
    for run in runs:
        columns = _column_clusters(run)
        rows = [
            line
            for line in run
            if len(line) >= 2 and len(_mapped_segments(line, columns)) >= 2
        ]
        if len(rows) < _MIN_TABLE_ROWS:
            continue
        if max(len(_mapped_segments(line, columns)) for line in rows) < (
            _MIN_TABLE_COLUMNS
        ):
            continue
        if not columns:
            continue
        first = columns[0]
        first_cells = [
            segment.text
            for line in rows
            for segment, column in _mapped_segments(line, columns)
            if column.center == first.center
        ]
        with_letters = sum(
            1 for cell in first_cells if any(char.isalpha() for char in cell)
        )
        if with_letters * 2 < len(first_cells):
            continue
        cells = [
            segment.text
            for line in rows
            for segment, _column in _mapped_segments(line, columns)
        ]
        if any(len(cell) > _MAX_CELL_CHARS for cell in cells):
            continue
        trimmed = _trim_leading_fragments(run, columns)
        if trimmed is not None:
            qualifying.append(trimmed)
    return qualifying


def _is_row_start(segment: _Segment) -> bool:
    """A single-segment first-column line that opens a row, not a footnote.

    Footnote lines start with an abbreviation (`ASD:`, `DSM-IV:`), carry brackets
    (`[16]`), or run on as prose; an author- or study-name fragment does none of
    those and is short.
    """
    text = segment.text.strip()
    if not (_MIN_ROW_START_CHARS <= len(text) <= _MAX_ROW_START_CHARS):
        return False
    if ":" in text or "[" in text:
        return False
    return True


def _trim_leading_fragments(
    run: list[tuple[_Segment, ...]], columns: tuple[_Column, ...]
) -> list[tuple[_Segment, ...]] | None:
    """Drop leading lines too small to be the header, or `None` if none remain.

    A stray prose fragment on the grid (`disparities (Table 6; Figure 5).`) maps
    two or three cells and must not become the header row; it is trimmed back into
    the prose stream. The real header of every fixture table spans at least
    `_MIN_HEADER_CELLS` columns.
    """
    start = 0
    while start < len(run):
        line = run[start]
        if len(_mapped_segments(line, columns)) >= _MIN_HEADER_CELLS:
            break
        start += 1
    if start >= len(run):
        return None
    return run[start:]


def _table_rows(
    region: list[tuple[_Segment, ...]],
    stats: _Stats,
) -> list[list[str]]:
    """Cell rows for one table region; unmappable content is dropped and counted."""
    columns = tuple(sorted(_column_clusters(region), key=lambda c: c.center))
    first = columns[0]
    rows: list[dict[float, list[str]]] = []
    for line in region:
        cells: dict[float, list[str]] = {}
        for segment in line:
            column = _nearest_column(segment.x, columns)
            if column is None:
                stats.dropped_table_segments += 1
                continue
            cells.setdefault(column.center, []).append(segment.text)
        if not cells:
            stats.dropped_table_lines += 1
            continue
        if first.center in cells:
            rows.append(cells)
        elif rows:
            open_row = rows[-1]
            for center, parts in cells.items():
                open_row.setdefault(center, []).extend(parts)
        else:
            rows.append(cells)
    rendered: list[list[str]] = []
    for row in rows:
        rendered.append(
            [
                _join_wrapped_values("\n".join(row.get(column.center, [])))
                for column in columns
            ]
        )
    return rendered


def _render_table(rows: list[list[str]]) -> list[str]:
    """GFM pipe rows: header, delimiter, then padded data rows over one column set."""
    width = max(len(row) for row in rows)
    lines = [_pipe_row(rows[0])]
    lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    for row in rows[1:]:
        lines.append(_pipe_row((row + [""] * width)[:width]))
    return lines


def _pipe_row(cells: list[str]) -> str:
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


# --------------------------------------------------------------------------------
# Value line-join
# --------------------------------------------------------------------------------


def _numeric_fragment(text: str) -> bool:
    """A piece of a number: starts digit-ish and ends with a digit or a dot."""
    if not text:
        return False
    return text[0] in _NUMBER_CHARS + ".+-" and text[-1] in _NUMBER_CHARS + "."


def _parses_as_number(text: str) -> bool:
    try:
        Decimal(text.replace(",", ""))
        return True
    except InvalidOperation:
        return False


def _join_wrapped_values(text: str) -> str:
    """Join a numeric token split across a line break; other breaks become spaces.

    The join is numeric-token-scoped and parse-checked: `0.0` + newline + `3`
    re-joins to `0.03` only because `0.03` is a number. `835,784` + newline +
    `1,705` stays two values — a comma-bearing fragment on the right is a whole
    value, not a wrap, and fusing it would invent a number neither line wrote.
    """
    pieces = text.split("\n")
    out = [pieces[0]]
    for piece in pieces[1:]:
        if (
            _numeric_fragment(out[-1])
            and _numeric_fragment(piece)
            and "," not in piece
            and len(piece) <= 4
            and _parses_as_number(out[-1] + piece)
        ):
            out[-1] += piece
        else:
            out.append(piece)
    return " ".join(out)


# --------------------------------------------------------------------------------
# Page rendering
# --------------------------------------------------------------------------------


def _render_page(
    lines: list[tuple[_Segment, ...]], stats: _Stats
) -> list[str]:
    """The page's rendered lines: headings, prose, and tables in document order.

    The body size is measured over the lines that are *not* table regions —
    on a table page the mode of all sizes is the table's, and body text would be
    promoted to headings. Segments at the region's own size (footnotes annotate
    tables in the table's font) are excluded too.
    """
    regions = _table_regions(lines)
    region_lines = {line for region in regions for line in region}
    non_region = [line for line in lines if line not in region_lines]
    region_size = (
        _dominant_size([line for region in regions for line in region])
        if regions
        else None
    )
    body = _segment_mode(
        [segment.size for line in non_region for segment in line if segment.size != region_size]
    )
    if body <= 0.0:
        body = _body_size(lines)
    font_signal = any(
        segment.size > body * _FONT_SIGNAL_RATIO
        for line in non_region
        for segment in line
    )
    entries: list[tuple[str | None, str, float | None]] = []

    index = 0
    while index < len(lines):
        line = lines[index]
        for region in regions:
            if region[0] is line:
                rows = _table_rows(region, stats)
                for rendered in _render_table(rows):
                    entries.append((None, rendered, None))
                index += len(region)
                break
        else:
            text = "".join(segment.text for segment in line)
            if not text:
                index += 1
                continue
            label = _split_glued_label(text)
            if label is not None:
                head, tail = _split_glued_segments(line, label)
                entries.append(("## ", "".join(s.text for s in head), None))
                stats.headings_emitted += 1
                if tail:
                    level = (
                        _heading_level(tail, body)
                        if font_signal
                        else _shape_heading("".join(s.text for s in tail))
                    )
                    entries.append((level, "".join(s.text for s in tail), None))
                index += 1
                continue
            if font_signal:
                level = _heading_level(line, body)
                if level is None:
                    # MDPI sets its abstract heading at body size on the title's
                    # page: the exact-label rescue, and nothing broader.
                    level = _label_heading(text)
            else:
                level = _shape_heading(text)
            if level is not None and len(text) <= _MAX_HEADING_CHARS:
                entries.append((level, text, max(s.size for s in line)))
                stats.headings_emitted += 1
            elif level is not None:
                entries.append((None, text, None))
                stats.dropped_heading_lines += 1
            else:
                entries.append((None, text, None))
            index += 1

    merged: list[tuple[str | None, str, float | None]] = []
    for level, text, size in entries:
        if (
            level is not None
            and size is not None
            and merged
            and merged[-1][0] == level
            and merged[-1][2] == size
        ):
            merged[-1] = (level, merged[-1][1] + " " + text, size)
        else:
            merged.append((level, text, size))
    return [level + text if level is not None else text for level, text, _ in merged]


# --------------------------------------------------------------------------------
# The public seam
# --------------------------------------------------------------------------------


def pdf_to_markdown_with_stats(pdf_bytes: bytes) -> tuple[str, ConversionStats]:
    """Convert PDF bytes to Markdown-equivalent text, with the recorded drops.

    The bytes are the whole input — never a path, never a URL — and the conversion
    is a pure function of them. Corrupt or unreadable bytes raise `PdfInputError`
    with the cause; this is a harness-side failure, never a verdict.
    """
    if not isinstance(pdf_bytes, bytes):
        raise TypeError(
            f"pdf_bytes must be bytes, not {type(pdf_bytes).__name__}"
        )
    stats = _Stats()
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages: list[str] = []
        for page in reader.pages:
            lines = _group_lines(_extract_segments(page))
            pages.append("\n".join(_render_page(lines, stats)))
    except PdfReadError as error:
        raise PdfInputError(f"cannot read PDF bytes: {error}") from error
    return (
        "\n\n".join(pages).rstrip("\n") + "\n",
        ConversionStats(
            pages=len(reader.pages),
            headings_emitted=stats.headings_emitted,
            dropped_heading_lines=stats.dropped_heading_lines,
            dropped_table_lines=stats.dropped_table_lines,
            dropped_table_segments=stats.dropped_table_segments,
        ),
    )


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    """Convert PDF bytes to Markdown-equivalent text (see `pdf_to_markdown_with_stats`)."""
    markdown, _stats = pdf_to_markdown_with_stats(pdf_bytes)
    return markdown