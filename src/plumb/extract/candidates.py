"""Every number in a paper, with where it is, what surrounds it, and which section.

This is the harness the selection rule will later be *measured against*, which is the
only reason it exists as a separate module. The plan (§0) keeps the two apart on
purpose: the owner labels these candidates claim / not-claim, the labels are committed,
and only then is a rule written. If one author wrote both, precision and recall would
measure whether the code implements the rule rather than whether the rule is right, and
the metric could not fail.

So the contract here is narrow and strange-looking on purpose:

**Exhaustive.** Every number, including the ones that are obviously not claims — years,
page numbers, DOIs, version strings, list markers. Dropping them would be *selection*,
and selection does not exist yet. Over-extraction is the correct failure direction: a
candidate the rule later discards costs a label, while a number never extracted is
invisible to precision, recall and the labeller alike.

**Judgement-free.** Nothing here decides what a number means. The section hint is read
off Markdown structure — a `## Results` heading, membership of a parsed table — and
never off the words around the number. A paper with no headings gets `other`
everywhere; an honest `other` is worth more than a guess that a later metric would
inherit as though it were a fact.

**No verdicts.** A `Candidate` is not a `Claim` and carries no judgement; building a
`Claim` is the admission gate's job, through deterministic grounding.

Two tokenization rules decide what "a number" is, and both are stated here because
they are judgements, however small:

- A number never *starts* inside a run of digits, so `412` is one candidate rather than
  `412`, `12` and `2`. This is also what splits `v1.2.3` into `1.2` and `3`.
- A leading `+`/`-` joins the number only when nothing word-like precedes it. `-0.5` in
  prose keeps its sign; `AUC-0.87` and `12-15` do not gain one, which is what stops
  `12-15` from being read as `12` and `-15`.

A trailing `%` or unit is deliberately *not* part of the candidate text: the unit
belongs to `Claim.units`, and the surrounding context keeps it visible to whatever
reads the candidate next.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final

from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.ordering import location_sort_key
from plumb.extract.tables import TableCell, parse_tables

__all__ = [
    "Candidate",
    "SECTION_ABSTRACT",
    "SECTION_HINTS",
    "SECTION_OTHER",
    "SECTION_REFERENCES",
    "SECTION_RESULTS",
    "SECTION_TABLE",
    "extract_candidates",
]


SECTION_ABSTRACT: Final = "abstract"
SECTION_RESULTS: Final = "results"
SECTION_TABLE: Final = "table"
SECTION_REFERENCES: Final = "references"

#: The honest default, and the most common value by far. Everything that is not a
#: recognised heading or a table cell is `other` — not "probably methods".
SECTION_OTHER: Final = "other"

#: The closed vocabulary. Closed because a hint reaches the labelling file and, later,
#: the selection rule; an invented value would arrive there looking like a structural
#: fact about the paper.
SECTION_HINTS: Final = frozenset(
    {
        SECTION_ABSTRACT,
        SECTION_RESULTS,
        SECTION_TABLE,
        SECTION_REFERENCES,
        SECTION_OTHER,
    }
)

#: Heading titles that map to a hint, after normalization. Deliberately tiny and
#: literal: adding "discussion", "bibliography" or "conclusions" is a deliberate edit
#: with a test, not a synonym list that grows until the hint means "whatever the model
#: thought the section was about". Note there is no entry mapping to `table` — that
#: hint comes from membership of a parsed table, never from a heading that says
#: "Table 2".
_HEADING_SECTIONS: Final = {
    SECTION_ABSTRACT: SECTION_ABSTRACT,
    SECTION_RESULTS: SECTION_RESULTS,
    SECTION_REFERENCES: SECTION_REFERENCES,
}

#: A number as a paper writes one. See the module docstring for the two lookbehinds;
#: they are the whole of the tokenization policy.
_NUMBER: Final = re.compile(
    r"(?<!\d)"
    r"(?:(?<!\w)[+-])?"
    r"(?:"
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"  # 10,000   1,234.5
    r"|\d+\.\d+"  # 0.87
    r"|(?<!\w)\.\d+"  # .001, but not the `.5678` of `xyz.5678`
    r"|\d+"  # 412
    r")"
    r"(?:[eE][+-]?\d+)?"  # 1e-5
)

#: An ATX heading, matched against one line. Up to three leading spaces is Markdown's
#: own allowance; a fourth would make the line a code block.
_HEADING: Final = re.compile(r"[ \t]{0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*")

#: A closing `###` sequence, which GFM requires to be preceded by whitespace.
_CLOSING_HASHES: Final = re.compile(r"\s+#+$")

#: `3.` / `3.1` / `A.2` style numbering in front of a heading title.
_HEADING_NUMBER: Final = re.compile(r"^\d+(?:\.\d+)*\.?[ \t]+")

#: A sentence terminator: run-final punctuation followed by whitespace or the end.
_TERMINATOR: Final = re.compile(r"[.!?]+(?=\s|$)")

#: A list enumerator at the start of a line — `1.` opening a reference. Its period is
#: not a full stop, and treating it as one leaves the first number of every reference
#: with `1.` as its entire context.
_ENUMERATOR: Final = re.compile(r"[ \t]*\d+")

#: Words whose trailing period is an abbreviation rather than a sentence end. A closed,
#: deliberately short list: it improves the *context* a human labeller reads and
#: nothing else, so it is not worth growing into a language model.
_ABBREVIATIONS: Final = frozenset(
    {"al", "approx", "cf", "e.g", "ed", "eds", "eq", "eqs", "et", "fig", "figs",
     "i.e", "no", "nos", "p", "pp", "ref", "refs", "tab", "vol", "vs"}
)

_BLANK: Final = "blank"
_HEADING_LINE: Final = "heading"
_TABLE_LINE: Final = "table"
_TEXT_LINE: Final = "text"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One number found in a paper, with enough around it to be labelled or grounded.

    - `text` — the number exactly as written, verbatim. `span` reproduces it.
    - `span` — character offsets into `normalize_text(paper)`, like every other
      offset in this package (`location.py`).
    - `context` — the sentence the number sits in, or the table cell if it is inside
      one. What a human reads to decide whether this is a claim.
    - `section_hint` — one of `SECTION_HINTS`, derived structurally. A *hint*: it says
      where in the document the number is, never what it means.

    There is no `confidence` and no `is_claim`. Both would be a judgement this phase is
    forbidden to make — the first is a model's opinion standing in for a re-derived
    value (`CLAUDE.md` #1), the second is the selection decision the plan defers so it
    can be scored against labels it did not author.
    """

    text: str
    span: CharSpan
    context: str
    section_hint: str

    def __post_init__(self) -> None:
        for name in ("text", "context", "section_hint"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(
                    f"Candidate.{name} must be a string, got "
                    f"{type(value).__name__}: {value!r}"
                )
        if not isinstance(self.span, CharSpan):
            raise TypeError(
                "Candidate.span must be a CharSpan into the normalized text, got "
                f"{type(self.span).__name__}: {self.span!r}"
            )
        if self.section_hint not in SECTION_HINTS:
            raise ValueError(
                f"unknown section hint {self.section_hint!r}; the vocabulary is "
                f"closed: {sorted(SECTION_HINTS)}"
            )


def _line_regions(text: str) -> tuple[tuple[int, int], ...]:
    """`(start, end)` of every line, `end` excluding the newline.

    Scanned rather than `splitlines()`, for the reason `tables.py` gives: only `\\n`
    may be treated as a line break, because it is the only break normalization leaves.
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


def _heading_title(line: str) -> str | None:
    """The normalized title of an ATX heading line, or `None` if it is not one.

    Normalization is syntactic only — closing hashes, section numbering, surrounding
    punctuation, case. `## 3. Results ##` and `## Results` are the same heading written
    two ways; nothing here reads what the words mean.
    """
    match = _HEADING.fullmatch(line)
    if match is None:
        return None
    title = _CLOSING_HASHES.sub("", (match[2] or "").strip())
    title = _HEADING_NUMBER.sub("", title.strip())
    return title.strip().strip(".:;,").strip().lower()


def _heading_hints(
    text: str, lines: tuple[tuple[int, int], ...]
) -> tuple[tuple[int, str], ...]:
    """Each heading's start offset and the section hint in force from there on.

    Nesting is resolved by **heading level**, not by meaning: a deeper heading inherits
    the section it sits inside unless its own title maps, so `### Secondary outcome`
    under `## Results` is still `results`, and the next `##` ends the section. That is
    the whole of the inheritance rule, and it is structural — which is what keeps a hint
    from becoming a guess about what a subsection is about.
    """
    stack: list[tuple[int, str]] = []
    hints: list[tuple[int, str]] = []
    for start, end in lines:
        match = _HEADING.fullmatch(text[start:end])
        if match is None:
            continue
        level = len(match[1])
        while stack and stack[-1][0] >= level:
            stack.pop()
        inherited = stack[-1][1] if stack else SECTION_OTHER
        title = _heading_title(text[start:end])
        hint = _HEADING_SECTIONS.get(title, inherited) if title else inherited
        stack.append((level, hint))
        # The heading line belongs to the section it opens, so a number in the heading
        # itself carries that hint.
        hints.append((start, hint))
    return tuple(hints)


def _line_kinds(
    text: str, lines: tuple[tuple[int, int], ...], table_spans: tuple[CharSpan, ...]
) -> tuple[str, ...]:
    """Classify each line, which is all the block structure the context needs.

    A heading is a block of its own even with no blank line under it — otherwise
    `## Results` would be prepended to the first sentence of every section it opens.
    """
    kinds: list[str] = []
    for start, end in lines:
        line = text[start:end]
        if not line.strip():
            kinds.append(_BLANK)
        elif _HEADING.fullmatch(line) is not None:
            kinds.append(_HEADING_LINE)
        elif any(
            span.start <= start and start < span.end for span in table_spans
        ):
            kinds.append(_TABLE_LINE)
        else:
            kinds.append(_TEXT_LINE)
    return tuple(kinds)


def _ends_a_sentence(text: str, terminator: re.Match[str]) -> bool:
    """Is this run of `.!?` a real sentence end, or punctuation that looks like one?

    Three exceptions, all cheap and all about *context quality* rather than
    correctness — a wrong split costs a labeller a readable context, never a verdict:

    - an enumerator (`1.` opening a reference),
    - a short closed list of abbreviations (`et al.`, `pp.`, `Fig.`),
    - a single letter, which in a paper is an author initial (`Smith, J. et al.`)
      far more often than a sentence that ends in one.

    A decimal point needs no exception: it is never followed by whitespace, so it
    never matches in the first place.
    """
    dot = terminator.start()
    line_start = text.rfind("\n", 0, dot) + 1
    if _ENUMERATOR.fullmatch(text[line_start:dot]) is not None:
        return False
    head = dot
    while head > line_start and (text[head - 1].isalpha() or text[head - 1] == "."):
        head -= 1
    word = text[head:dot]
    if len(word) == 1 and word.isalpha():
        return False
    return word.lower() not in _ABBREVIATIONS


def _sentences(text: str, block_start: int, block_end: int) -> list[tuple[int, str]]:
    """One prose block, split into `(start, sentence)` pairs in document order.

    Interior newlines are kept inside a sentence: a hard-wrapped sentence is one
    sentence, and rewriting its whitespace would produce a context that does not
    appear in the paper.
    """
    sentences: list[tuple[int, str]] = []
    start = block_start
    for terminator in _TERMINATOR.finditer(text, block_start, block_end):
        if not _ends_a_sentence(text, terminator):
            continue
        end = terminator.end()
        sentences.append((start, text[start:end].strip()))
        start = end
        while start < block_end and text[start].isspace():
            start += 1
    if start < block_end or not sentences:
        sentences.append((start, text[start:block_end].strip()))
    return sentences


def _context_regions(
    text: str, lines: tuple[tuple[int, int], ...], kinds: tuple[str, ...]
) -> tuple[tuple[int, str], ...]:
    """Every context in the document, as `(start, text)` in document order.

    The regions tile the whole document, so the context of an offset is simply the
    last region beginning at or before it — which a monotonic cursor finds in one pass
    over an ordered scan, with no search per number.

    **That is the reason this is computed up front rather than per candidate.** The
    natural spelling — walk outwards from a number's line to find its paragraph, then
    split that paragraph into sentences — is quadratic in the paragraph, and a paper
    is one long document rather than the twenty-line fixture it is tested on. It ran
    for twenty-two seconds on a four-thousand-line paper before this pass existed.

    Prose blocks run across line breaks so a hard-wrapped sentence stays whole, and
    stop at a blank line, a heading or a table — the three things that are never part
    of the sentence beside them. A heading or table line is one region: a heading is a
    title, not prose, and splitting `## 3. Results` at the enumerator's period would
    leave `## 3.` as the entire context of its `3`.
    """
    regions: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        start, end = lines[index]
        if kinds[index] != _TEXT_LINE:
            regions.append((start, text[start:end].strip()))
            index += 1
            continue
        while index + 1 < len(lines) and kinds[index + 1] == _TEXT_LINE:
            index += 1
        regions.extend(_sentences(text, start, lines[index][1]))
        index += 1
    return tuple(regions)


def extract_candidates(raw: str) -> tuple[Candidate, ...]:
    """Every number in `raw`, with context, in deterministic document order.

    `raw` is normalized on the way in and every offset indexes that normalized text —
    the same rule `tables.py` and `hashing.py` follow, so a CRLF checkout of a paper
    produces identical candidates.

    Order is `ordering.location_sort_key` then the candidate text, which is total: the
    scan already emits candidates in document order, and sorting on the shared key
    makes that a stated contract rather than a property of the scan. The text
    tie-breaker cannot fire today (two candidates cannot share a span) and is there so
    the key stays total if that ever changes — a tie would otherwise fall back to
    extraction order, which is exactly what these helpers exist to remove.

    Never raises on malformed input, and never returns a `Claim`: admission is a
    separate, deterministic gate.
    """
    text = normalize_text(raw)
    lines = _line_regions(text)
    tables = parse_tables(text)
    cells: tuple[TableCell, ...] = tuple(
        cell for table in tables for cell in table.cells
    )
    kinds = _line_kinds(text, lines, tuple(table.span for table in tables))
    hints = _heading_hints(text, lines)
    regions = _context_regions(text, lines, kinds)

    candidates: list[Candidate] = []
    # Cursors rather than a search per number: the numbers, the cells, the headings and
    # the context regions are all in document order, so each cursor only moves forward
    # and the whole pass is linear in the paper.
    cell_cursor = 0
    hint_cursor = -1
    region_cursor = 0

    for match in _NUMBER.finditer(text):
        offset = match.start()
        while cell_cursor < len(cells) and cells[cell_cursor].span.end <= offset:
            cell_cursor += 1
        while hint_cursor + 1 < len(hints) and hints[hint_cursor + 1][0] <= offset:
            hint_cursor += 1
        while (
            region_cursor + 1 < len(regions)
            and regions[region_cursor + 1][0] <= offset
        ):
            region_cursor += 1

        cell = cells[cell_cursor] if cell_cursor < len(cells) else None
        if cell is not None and cell.span.start <= offset:
            # A table cell is the more specific structural container, and it is also
            # the honest context: the sentence around a table row is not a sentence.
            context = cell.text
            hint = SECTION_TABLE
        else:
            # `regions` is never empty: every line yields at least one, and every
            # document has at least one line.
            context = regions[region_cursor][1]
            hint = hints[hint_cursor][1] if hint_cursor >= 0 else SECTION_OTHER

        candidates.append(
            Candidate(
                text=match.group(),
                span=CharSpan(match.start(), match.end()),
                context=context,
                section_hint=hint,
            )
        )

    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                location_sort_key(candidate.span),
                candidate.text,
            ),
        )
    )
