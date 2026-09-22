"""Deterministic PDF-to-Markdown text conversion on the pinned pypdf.

The pipeline, per document:

1. **Runs** — pypdf's visitor API yields every text run with its position (the
   text-matrix translation `(x, y)`), its text matrix `tm`, and font size. The
   rendered size of a run is `font_size * tm[0]` (the horizontal scale), which is
   the same unit across all five fixtures — Cureus and the journals that scale
   their content stream report `font_size` in their own space. Runs whose text is
   empty or whitespace are discarded; a run at exactly `(0, 0)` is a duplicate
   overlay stream (Springer draws its text twice) and is dropped and counted.
2. **Direction** — the sign of `tm[3]` (the y scale) is the page's y convention:
   Cureus flips it (`-1`, top-down, reading order = ascending y); the rest do not
   (`+1`, reading order = descending y). One document-level direction is the
   mode of the sign across every run.
3. **Lines** — runs are grouped into lines by y key. With `tol=0` the key is the
   rounded y, exactly as before. With a small tolerance and the page's char
   advance, a near-baseline run (a superscript `2`, a citation fragment offset by
   a couple of points) joins the line whose x-span contains it; a different line
   a few points off in y (the editorial block on a title page) never does.
4. **Furniture** — running heads and footers are dropped deterministically: a
   line in the top or bottom 10% band of its page whose runs' text repeats in the
   same band on at least two pages, counted by character (a footer that carries
   the page number still repeats mostly). Drops are recorded in
   `ConversionStats.dropped_furniture_lines`, never silent.
5. **Columns** — a page is two-column when two dense line-start clusters sit on
   opposite sides of the page's x-center with a low-density band between them;
   table lines are excluded first (a table's columns are not a text layout) and
   a single-column page whose lines merely carry in-line citations does not fire.
   Column-bound lines are split at the gutter, full-width lines (title, abstract
   banner) stay whole, and the page is emitted as full-width + left column in
   reading y order, then the right column.
6. **Headings** — the body size is the most common segment size; heading sizes
   are ranked across the document, so each journal's own scale decides the level:
   the largest heading size is `# ` (the title), the next `## ` (sections), the
   rest `### `/`#### ` (subsections). A subsection heading inherits the section's
   hint (`###` under `## Results` is still `results`), which is what keeps the
   claims of Oxford's and Springer's Results subsections recoverable. The line-
   shape fallback still applies where no size signal exists, gated to lines whose
   runs sit in one x-band and that do not open with an article or lowercase word.
   A known section label glued to prose (`AbstractThis review...`) splits first.
7. **Tables** — unchanged: column clusters, maximal runs, GFM pipe rows with the
   value line-join inside cells.

Determinism: every ordering below is a sort or an index, never set or dict
iteration; the only arithmetic is on pypdf's own coordinates. Byte identity
across processes is pinned in `tests/pdf/test_convert.py`.
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

#: A line is a heading candidate when its largest segment is at least this much
#: larger than the page body; a tiny difference (MDPI sets part of its body at
#: 10.0pt against a 9.96pt mode) is no signal at all.
_FONT_SIGNAL_RATIO = 1.05

#: A line of heading size is a title at twice the body size.
_TITLE_RATIO = 2.0

#: The `## ` section-heading threshold: clearly larger than the body, or at least
#: this many points above it (the absolute cushion keeps a caption-polluted body
#: mode from promoting prose — a page whose figure captions outnumber the prose
#: has a body mode of the caption size).
_HEADING_RATIO = 1.1
_HEADING_CUSHION = 1.5

#: Heading-size lines longer than this are prose (counted as dropped headings).
_MAX_HEADING_CHARS = 240

#: A `### `-level line longer than this is prose, not a subheading — the real
#: subheadings of the fixtures are short; the long promoted lines are prose that
#: merely sat a little above a caption-polluted body mode.
_MAX_SUBHEADING_CHARS = 60

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

#: The first word of a shape-heading line may not be one of these: a prose line
#: that merely starts with an article or a subject is not a heading.
_HEADING_OPENERS = frozenset(
    {
        "the", "a", "an", "this", "these", "those", "we", "our", "in", "on",
        "of", "for", "with", "to", "is", "are", "was", "were", "it", "its",
        "as", "at", "by", "from", "that", "which", "and", "or", "but", "not",
        "however",
    }
)

#: The y tolerance for grouping a near-baseline run into a line.
_Y_TOLERANCE = 5.0

#: The furniture bands: the top and bottom 10% of a page's y-extent.
_FURNITURE_BAND = 0.10

#: The gutter (two-column band) is at least this wide and both column-start
#: clusters hold at least this many lines.
_GUTTER_MIN_WIDTH = 8.0
_CENTER_TOLERANCE = 0.2
_MIN_SIDE_LINES = 8

#: A crossing line is split only when its right-hand runs sit within this far of
#: the right column's start — Springer's right-edge `-` markers are not columns.
_SPLIT_MARGIN = 40.0

#: The fallback per-char advance used to estimate run extents.
_CHAR_ADVANCE_FALLBACK = 0.5

#: Distinct heading sizes ranked per document need at least this many lines, so a
#: CFF-decoding artifact on one or two lines cannot steal a heading level.
_MIN_HEADING_SIZE_LINES = 4

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
    dropped_furniture_lines: int = 0


class PdfInputError(RuntimeError):
    """The PDF bytes could not be read; a harness-side failure, never a verdict."""


@dataclass(slots=True)
class _Stats:
    """Mutable accumulation for `ConversionStats`; never escapes the conversion."""

    headings_emitted: int = 0
    dropped_heading_lines: int = 0
    dropped_table_lines: int = 0
    dropped_table_segments: int = 0
    dropped_furniture_lines: int = 0


@dataclass(frozen=True, slots=True)
class _Segment:
    """One text run on the page: x position, rendered size, and its text."""

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


def _extract_runs(page) -> list[tuple[float, float, float, str, float, float]]:
    """`(y, x, rendered_size, text, y_scale, x_scale)` for every text run.

    The rendered size is `font_size * tm[0]` (the text matrix's horizontal
    scale): it is the same physical unit for Cureus (which flips and scales its
    content stream), for Oxford and Springer (which report `font_size == 1.0`
    with the scale in the matrix), and for MDPI and Sensors.
    """
    runs: list[tuple[float, float, float, str, float, float]] = []

    def visitor(text, cm, tm, font_dict, font_size) -> None:
        if text is None or not text.strip():
            return
        size = (font_size or 0.0) * tm[0]
        for part in text.split("\n"):
            if part.strip():
                runs.append((tm[5], tm[4], size, part, tm[3], tm[0]))

    page.extract_text(visitor_text=visitor)
    return runs


def _drop_overlay_runs(
    runs: list[tuple[float, float, float, str, float, float]],
) -> list[tuple[float, float, float, str, float, float]]:
    """Drop runs drawn at exactly `(0, 0)` — Springer's duplicate overlay stream."""
    return [run for run in runs if not (run[1] == 0.0 and run[0] == 0.0)]


def _document_direction(
    pages_runs: list[list[tuple[float, float, float, str, float, float]]],
) -> float:
    """The document's y convention: `-1.0` is top-down, `+1.0` bottom-up.

    The sign of the text matrix's y scale is the page's own coordinate system.
    Cureus renders with an inverted y (reading order = ascending y); the other
    four fixtures use PDF user space (reading order = descending y).
    """
    counts: dict[float, int] = {}
    for runs in pages_runs:
        for run in runs:
            sign = 1.0 if run[4] >= 0 else -1.0
            counts[sign] = counts.get(sign, 0) + 1
    if not counts:
        return 1.0
    return min(counts, key=lambda sign: (-counts[sign], sign))


def _run_end(run, advance: float) -> float:
    """A run's estimated right edge: start plus the advance times its length."""
    return run[1] + advance * len(run[3])


def _group_lines(
    runs: list[tuple[float, float, float, str, float, float]],
    *,
    tol: float = 0.0,
    advance: float | None = None,
) -> list[tuple[int, list[tuple[float, float, float, str, float, float]]]]:
    """Runs grouped into lines by y, sorted by x within a line.

    With `tol=0` the key is the rounded y (the seam's line model). With a small
    tolerance and the page's char advance, a near-baseline run joins the line
    whose x-span contains it; a run outside the span is a different line.
    """
    by_y: dict[int, list[tuple[float, float, float, str, float, float]]] = {}
    for run in runs:
        by_y.setdefault(round(run[0]), []).append(run)

    clusters: list[tuple[list[int], list]] = []
    for y in sorted(by_y):
        members = by_y[y]
        if clusters and y - clusters[-1][0][0] <= tol:
            if advance is None or any(
                run[1] <= max(_run_end(r, advance) for r in clusters[-1][1])
                for run in members
            ):
                clusters[-1][0].append(y)
                clusters[-1][1].extend(members)
                continue
        clusters.append(([y], list(members)))

    lines: list[tuple[int, list]] = []
    for ys, members in clusters:
        members.sort(key=lambda r: (r[1], r[0]))
        lines.append((ys[0], members))
    return lines


def _page_advance(lines) -> float:
    """The page's median per-character advance, from adjacent runs on a line.

    The median is robust to citation fragments and superscripts: a fragment's gap
    to the next run is its own width over its own length, so the median stays the
    body's advance.
    """
    gaps: list[float] = []
    for _anchor, members in lines:
        for i in range(len(members) - 1):
            gap = members[i + 1][1] - members[i][1]
            if gap > 1.0 and len(members[i][3]) > 0:
                gaps.append(gap / len(members[i][3]))
    gaps = [gap for gap in gaps if 0.5 <= gap <= 12.0]
    if gaps:
        return sorted(gaps)[len(gaps) // 2]
    scales = [run[5] for _a, members in lines for run in members if run[5] > 0]
    if not scales:
        return 1.0
    return _CHAR_ADVANCE_FALLBACK * sorted(scales)[len(scales) // 2]


# --------------------------------------------------------------------------------
# Furniture (headers and footers)
# --------------------------------------------------------------------------------


def _furniture_indices(
    pages_lines: list[list[tuple[int, list]]], direction: float
) -> list[set[int]]:
    """Per-page line indices to drop: extreme-band lines whose runs repeat.

    A line is furniture when it sits in the top or bottom 10% band of its page
    and the character-majority of its runs' texts repeat in the same band on at
    least two pages. Repeating by character means a footer carrying the page
    number still drops (the citation text outweighs the digits); a body line in
    the band that does not repeat survives.
    """
    bands = []
    for lines in pages_lines:
        ys = [anchor for anchor, _members in lines]
        if not ys:
            bands.append(None)
            continue
        lo, hi = min(ys), max(ys)
        span = max(hi - lo, 1.0)
        if direction < 0:  # top-down: top = low y
            top = lambda y: y <= lo + _FURNITURE_BAND * span
            bottom = lambda y: y >= hi - _FURNITURE_BAND * span
        else:
            top = lambda y: y >= hi - _FURNITURE_BAND * span
            bottom = lambda y: y <= lo + _FURNITURE_BAND * span
        bands.append((top, bottom))

    top_counts: dict[str, int] = {}
    bottom_counts: dict[str, int] = {}
    for lines, band in zip(pages_lines, bands):
        if band is None:
            continue
        top, bottom = band
        for anchor, members in lines:
            table = top if top(anchor) else (bottom if bottom(anchor) else None)
            if table is None:
                continue
            counts = top_counts if table is top else bottom_counts
            for run in members:
                counts[run[3]] = counts.get(run[3], 0) + 1

    dropped: list[set[int]] = []
    for lines, band in zip(pages_lines, bands):
        page_dropped: set[int] = set()
        if band is None:
            dropped.append(page_dropped)
            continue
        top, bottom = band
        for idx, (anchor, members) in enumerate(lines):
            if not members:
                continue
            in_top = top(anchor)
            in_bottom = bottom(anchor)
            if not (in_top or in_bottom):
                continue
            counts = top_counts if in_top else bottom_counts
            repeat_chars = sum(len(run[3]) for run in members if counts[run[3]] >= 2)
            total_chars = sum(len(run[3]) for run in members)
            if total_chars and repeat_chars * 2 >= total_chars:
                page_dropped.add(idx)
        dropped.append(page_dropped)
    return dropped


# --------------------------------------------------------------------------------
# Two-column layout
# --------------------------------------------------------------------------------


def _table_lines(lines) -> set[int]:
    """Line indices that the table detector would reconstruct as tables."""
    seg_lines = [
        tuple(sorted((_Segment(run[1], run[2], run[3]) for run in members), key=lambda s: s.x))
        for _anchor, members in lines
    ]
    regions = _table_regions(seg_lines)
    region_set = {line for region in regions for line in region}
    return {i for i, line in enumerate(seg_lines) if line in region_set}


def _detect_gutter(
    lines: list[tuple[int, list]], advance: float
) -> tuple[float, float] | None:
    """`(g1, g2)` of the page's gutter, or `None` when the page is not two-column.

    Two dense line-start clusters must sit on opposite sides of the page's
    x-center, with a low-density band at least `_GUTTER_MIN_WIDTH` wide between
    their content. A line counts toward a cluster when any of its runs starts
    there, so a merged left+right line votes for both columns. Table lines are
    excluded first — a table's columns are not a text layout — and the nearest-
    to-center band wins.
    """
    tables = _table_lines(lines)
    lines = [line for i, line in enumerate(lines) if i not in tables]
    if len(lines) < _MIN_SIDE_LINES * 2:
        return None
    runs = [run for _a, members in lines for run in members]
    page_min = min(run[1] for run in runs)
    page_max = max(run[1] for run in runs)
    center = (page_min + page_max) / 2
    line_starts = sorted(
        {round(min(run[1] for run in members), 1) for _a, members in lines}
    )
    clusters: list[list[float]] = []
    for start in line_starts:
        if clusters and start - clusters[-1][-1] <= _X_TOLERANCE:
            clusters[-1].append(start)
        else:
            clusters.append([start])

    counted: list[tuple[list[float], list]] = []
    for cluster in clusters:
        cset = set(cluster)
        lines_in = [
            (anchor, members)
            for anchor, members in lines
            if any(round(run[1], 1) in cset for run in members)
        ]
        if len(lines_in) >= _MIN_SIDE_LINES:
            counted.append((cluster, lines_in))

    candidates: list[tuple[tuple[float, float], float]] = []
    for ci in range(len(counted)):
        for cj in range(ci + 1, len(counted)):
            _ca, lines_a = counted[ci]
            cb, lines_b = counted[cj]
            g2 = cb[0]
            ends_a = [
                max(_run_end(run, advance) for run in members)
                for _anchor, members in lines_a
                if max(_run_end(run, advance) for run in members)
                <= g2 - _GUTTER_MIN_WIDTH
            ]
            if not ends_a:
                continue
            g1 = max(ends_a)
            if g2 - g1 < _GUTTER_MIN_WIDTH:
                continue
            gmid = (g1 + g2) / 2
            if abs(gmid - center) > _CENTER_TOLERANCE * (page_max - page_min):
                continue
            candidates.append(((g1, g2), abs(gmid - center)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[1])
    return candidates[0][0]


def _split_and_assign(
    lines: list[tuple[int, list]],
    gutter: tuple[float, float],
    advance: float,
) -> tuple[list, list, list]:
    """Full-width, left-column and right-column lines after splitting at the gutter.

    A line crossing the gutter is split when its right-hand runs start within
    `_SPLIT_MARGIN` of the right column (a genuinely merged left+right line);
    otherwise it stays whole as a full-width line (a title or abstract banner
    with a stray margin marker).
    """
    g1, g2 = gutter
    full: list = []
    left: list = []
    right: list = []
    for anchor, members in lines:
        xmin = min(run[1] for run in members)
        xmax = max(_run_end(run, advance) for run in members)
        if xmax <= g1 + 0.5:
            left.append((anchor, members))
            continue
        if xmin >= g2 - 0.5:
            right.append((anchor, members))
            continue
        right_runs = [run for run in members if run[1] >= g2 - 0.5]
        left_runs = [run for run in members if run[1] < g2 - 0.5]
        if (
            left_runs
            and right_runs
            and (min(run[1] for run in right_runs) - g2) <= _SPLIT_MARGIN
        ):
            left.append((anchor, left_runs))
            right.append((anchor, right_runs))
        else:
            full.append((anchor, members))
    return full, left, right

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


def _heading_ranks(
    pages_kept: list[list[tuple[int, list]]],
) -> dict[float, str]:
    """Heading size -> level prefix, ranked by size across the document.

    The largest heading size is the title (`# `), the next the section heading
    (`## `), and the rest subsections (`### `, `#### `). Ranking within the
    document rather than by a fixed ratio lets each journal's own scale decide:
    Oxford's sections and subs (11.0 / 10.0) and Springer's (12.0 / 11.0) both
    land on the correct levels even though the absolute ratios differ. Sizes
    seen on fewer than `_MIN_HEADING_SIZE_LINES` lines are artifacts of a
    font-decoding gap and are ignored.
    """
    candidates: dict[float, int] = {}
    for lines in pages_kept:
        body = _segment_mode([run[2] for _a, members in lines for run in members])
        if body <= 0.0:
            continue
        for _anchor, members in lines:
            top = max(run[2] for run in members)
            if top > body * _FONT_SIGNAL_RATIO:
                size = round(top, 2)
                candidates[size] = candidates.get(size, 0) + 1
    sizes = [
        size
        for size, count in sorted(candidates.items(), reverse=True)
        if count >= _MIN_HEADING_SIZE_LINES
    ]
    prefixes = ("# ", "## ", "### ", "#### ")
    return {
        size: prefixes[i] if i < len(prefixes) else "#### "
        for i, size in enumerate(sizes)
    }


def _heading_level(
    line: tuple[_Segment, ...],
    body: float,
    levels: dict[float, str] | None = None,
) -> str | None:
    """The heading level for a line under the size rule, or `None`.

    With the document-level `levels` the prefix is looked up by size; a long line
    is never a subheading. Without it, the per-page thresholds apply: `# ` at
    twice the body, `## ` clearly above it (with an absolute cushion so a
    caption-polluted body cannot promote prose), `### ` just above it.
    """
    if body <= 0.0:
        return None
    top = max(segment.size for segment in line)
    if top < body * _FONT_SIGNAL_RATIO:
        return None
    if levels:
        if sum(len(s.text) for s in line) > _MAX_SUBHEADING_CHARS:
            return None
        size = round(top, 2)
        rank = levels.get(size)
        if rank is not None:
            return rank
        return "### "
    if top >= body * _TITLE_RATIO:
        return "# "
    if top > max(body * _HEADING_RATIO, body + _HEADING_CUSHION):
        return "## "
    if sum(len(s.text) for s in line) > _MAX_SUBHEADING_CHARS:
        return None
    return "### "


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


def _shape_heading_gated(text: str, segments: tuple[_Segment, ...]) -> str | None:
    """The shape fallback, gated to single x-band lines that open like headings.

    A line whose runs span two x-bands (a table row fragment) is not a heading,
    and neither is a line opening with an article or a lowercase word — those
    are prose fragments the shape rules would over-promote on font-less pages.
    """
    if len(segments) >= 2:
        xs = [segment.x for segment in segments]
        if max(xs) - min(xs) > 8.0:
            return None
    words = text.strip().split()
    if words:
        first = words[0].strip(",.()[]-;:")
        if not words[0][0].isupper() or first.lower() in _HEADING_OPENERS:
            return None
        if len(words) == 1:
            single = first
            if single.isalpha() and single[0].isupper() and 4 <= len(single) < 5:
                return "## "
    return _shape_heading(text)


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


def _numbered_label_heading(text: str) -> str | None:
    """`"## "` for a short numbered section heading like `3. Results`.

    MDPI and Sensors number their sections (`1. Introduction`, `3. Results`,
    `4. Experimental Setup`) at a size just above the body that the size rule
    does not promote; the numbered form is a section heading, never a list item
    (a list item carries punctuation or continues the sentence).
    """
    if re.match(r"^\d{1,2}\.\s+[A-Z][A-Za-z ]{2,59}$", text.strip()):
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


def _join_runs(segments) -> str:
    """Join a line's runs, inserting a space at a run junction a word needs.

    The CFF font gap on Oxford drops the inter-run space: `Table 3` plus
    `compares the performance...` would read `Table 3compares`. When a run ends
    with a digit, `%`, `)` or `,` and the next run opens with a letter, the
    junction is a word boundary the font swallowed.
    """
    out = ""
    for segment in segments:
        if (
            out
            and out[-1] in "0123456789%),"
            and segment.text[0].isalpha()
        ):
            out += " "
        out += segment.text
    return out


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
    lines: list[tuple[_Segment, ...]],
    stats: _Stats,
    levels: dict[float, str] | None = None,
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
            text = _join_runs(line)
            if not text:
                index += 1
                continue
            label = _split_glued_label(text)
            if label is not None:
                head, tail = _split_glued_segments(line, label)
                entries.append(("## ", _join_runs(head), None))
                stats.headings_emitted += 1
                if tail:
                    level = (
                        _heading_level(tail, body, levels)
                        if font_signal
                        else _shape_heading_gated(_join_runs(tail), tail)
                    )
                    entries.append((level, _join_runs(tail), None))
                index += 1
                continue
            if font_signal:
                level = _heading_level(line, body, levels)
                if level is None:
                    # MDPI sets its abstract heading at body size on the title's
                    # page: the exact-label rescue, and nothing broader.
                    level = _label_heading(text)
                elif text.strip().lower() == "abstract" and level != "## ":
                    # The seam's abstract span is `## Abstract` verbatim; the
                    # exact label is always a level-2 section heading, whatever
                    # its size on the title page.
                    level = "## "
                if level is None:
                    level = _numbered_label_heading(text)
            else:
                level = _shape_heading_gated(text, line)
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


def _convert(pdf_bytes: bytes) -> tuple[str, _Stats, int]:
    """The deterministic conversion; the form-XObject limit is raised around it."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_count = len(reader.pages)
    pages_runs = [_drop_overlay_runs(_extract_runs(page)) for page in reader.pages]
    direction = _document_direction(pages_runs)
    pages_lines = [_group_lines(runs) for runs in pages_runs]
    furniture = _furniture_indices(pages_lines, direction)
    pages_kept = [
        [line for i, line in enumerate(lines) if i not in dropped]
        for lines, dropped in zip(pages_lines, furniture)
    ]
    levels = _heading_ranks(pages_kept)
    stats = _Stats()
    out_pages: list[str] = []
    for runs, kept, dropped in zip(pages_runs, pages_kept, furniture):
        advance = _page_advance(kept)
        gutter = _detect_gutter(kept, advance)
        kept_runs = [run for _a, members in kept for run in members]
        soft = _group_lines(kept_runs, tol=_Y_TOLERANCE, advance=advance)
        if gutter is not None:
            full, left, right = _split_and_assign(soft, gutter, advance)
            rev = direction > 0
            ordered = sorted(full + left, key=lambda item: item[0], reverse=rev)
            ordered += sorted(right, key=lambda item: item[0], reverse=rev)
        else:
            ordered = sorted(soft, key=lambda item: item[0], reverse=(direction > 0))
        stats.dropped_furniture_lines += len(dropped)
        seg_lines = [
            tuple(_Segment(run[1], run[2], run[3]) for run in members)
            for _anchor, members in ordered
        ]
        out_pages.append("\n".join(_render_page(seg_lines, stats, levels)))
    return "\n".join(out_pages).rstrip("\n") + "\n", stats, page_count


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
    try:
        import pypdf

        with pypdf.apply_configuration(
            xform_maximum_invocations_per_extraction=1_000_000
        ):
            markdown, stats, page_count = _convert(pdf_bytes)
    except PdfReadError as error:
        raise PdfInputError(f"cannot read PDF bytes: {error}") from error
    return (
        markdown,
        ConversionStats(
            pages=page_count,
            headings_emitted=stats.headings_emitted,
            dropped_heading_lines=stats.dropped_heading_lines,
            dropped_table_lines=stats.dropped_table_lines,
            dropped_table_segments=stats.dropped_table_segments,
            dropped_furniture_lines=stats.dropped_furniture_lines,
        ),
    )


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    """Convert PDF bytes to Markdown-equivalent text (see `pdf_to_markdown_with_stats`)."""
    markdown, _stats = pdf_to_markdown_with_stats(pdf_bytes)
    return markdown
