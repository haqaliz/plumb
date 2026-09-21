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
- A leading `+`/`-` joins the number only when nothing word-like *or a percent sign*
  precedes it. `-0.5` in prose keeps its sign; `AUC-0.87` and `12-15` do not gain one,
  which is what stops `12-15` from being read as `12` and `-15`. The percent is there
  because a minus cannot directly follow one in any notation: `%` is not word-like, so
  without it `0.4%-1.7%` yielded `-1.7`, a negative number from a paper reporting a
  positive one — and it grounded and parsed, so nothing downstream refused it.

A trailing `%` or unit is deliberately *not* part of the candidate text: the unit
belongs to `Claim.units`, and the surrounding context keeps it visible to whatever
reads the candidate next.

**A composite value is one candidate.** A paper does not only write bare numbers, and
`p < 0.001`, `0.85 ± 0.03`, `12–15` and `95% CI [0.81, 0.93]` are each *one* value
written with notation. Emitting their pieces separately is not neutral over-extraction:
the `0.001` of `p < 0.001` admitted on its own asserts *p = 0.001*, a number the paper
never wrote, and a re-derived `0.0009` would then read as a contradiction. So the scan
emits the whole notation, and the pieces do not survive beside it — `0.001` next to
`p < 0.001` would also be counted twice by any later metric.

Three rules keep that widening from inventing values, and they are the whole of the
policy:

- **A composite is emitted only where `value.py` would parse it.** The patterns below
  are `parse_value`'s patterns, so extraction can never hand the admission gate a span
  the value parser then refuses. Where the two disagree, extraction stays narrow: a
  hyphen is not a range separator here because it is not one there, and `95% CI:
  0.4%-1.7%` — the form the real fixtures use — is left as its pieces rather than
  emitted as a candidate nothing can read.
- **The marker, not the bracket, makes an interval.** `[30,31]` is a citation and
  `(6,12)` is a degrees-of-freedom pair; both parse as `Interval` if handed to
  `parse_value` alone, and joining them would merge two numbers the paper kept apart.
  An explicit `CI` is required.
- **A composite never crosses a line break.** Only spaces and tabs may sit inside one,
  so a wrapped line, a table row and a cell boundary all stay intact.

The `%` is handled at both ends and the asymmetry is deliberate. A *trailing* `%` stays
out, as it does for a bare number (`12–15%` yields `12–15`). The *leading* `95%` of
`95% CI [...]` stays in: it is the confidence level rather than a unit, and `Interval`
requires that it never surface as an endpoint or as a `Point` of its own — which is
exactly what leaving it outside the candidate would do.
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
    r"(?:(?<![\w%])[+-])?"
    r"(?:"
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"  # 10,000   1,234.5
    r"|\d+\.\d+"  # 0.87
    r"|(?<!\w)\.\d+"  # .001, but not the `.5678` of `xyz.5678`
    r"|\d+"  # 412
    r")"
    r"(?:[eE][+-]?\d+)?"  # 1e-5
)

#: The bare-number pattern as a string, so every operand of every composite below is
#: tokenized by the *same* rule as a standalone number. Re-spelling it per composite is
#: how the two grammars drift apart, and a drift here is invisible: the composite would
#: still ground, still parse, and quietly disagree with `study_parameters` about what a
#: number is.
_OPERAND: Final = _NUMBER.pattern

#: Only spaces and tabs inside a composite, never a newline. A number ending one line
#: and a dash opening the next is a coincidence of hard wrapping, not a range, and a
#: span that crossed the break could also run out of one table cell into another.
_GAP: Final = r"[ \t]*"

#: `95% CI`, `CI`, `95% CrI` — a confidence or credible interval, with the confidence
#: level inside the marker where it belongs. **Required**, and it is the whole of the
#: discrimination: without it the patterns below read citation runs (`[30,31]`) and
#: degrees-of-freedom pairs (`(6,12)`) as intervals, and in the fixture corpus those
#: are the *only* bracketed pairs there are. The lookbehind keeps the `ci` of a longer
#: word from opening one, and `[Rr]?` admits `CrI` without admitting `CASI`.
_CI_MARKER: Final = rf"(?:{_OPERAND}{_GAP}%{_GAP})?(?<![A-Za-z])[Cc][Rr]?[Ii]"

#: `95% CI [0.81, 0.93]`, `CI (0.81, 0.93)`.
_INTERVAL_BRACKETED: Final = (
    rf"{_CI_MARKER}{_GAP}[\[(]{_GAP}{_OPERAND}{_GAP},{_GAP}{_OPERAND}{_GAP}[\])]"
)

#: The separators an interval is written with *after a marker*. The ASCII hyphen is
#: here and nowhere else in this module: it is the commonest real spelling
#: (`95% CI: 0.4%-1.7%`, 16 of 29 in the corpus), and after `CI:` it cannot be read as
#: a subtraction or a sign, because the notation has already said what it is. Outside
#: this context `12-15` is still two numbers — see `_RANGE`.
_INTERVAL_SEPARATOR: Final = r"[-–—,]"

#: `95% CI: 0.4%-1.7%`, `95% CI: -5.432, -4.092`, `95% CI 1.66–2.54`.
#:
#: Two branches, and the asymmetry between them is the `%` rule applied honestly. A
#: percent sign *between* the endpoints is interior notation: drop it and the text no
#: longer reads as the paper wrote it. A percent sign only at the *end* is a trailing
#: unit like any other and stays out, exactly as it does for `12–15%` and for a bare
#: number. So both endpoints carry one or neither does; the mixed spelling
#: (`0.4-1.7%`) takes the second branch and leaves the trailing unit behind.
_INTERVAL_MARKED: Final = (
    rf"{_CI_MARKER}{_GAP}:?{_GAP}"
    rf"(?:{_OPERAND}{_GAP}%{_GAP}{_INTERVAL_SEPARATOR}{_GAP}{_OPERAND}{_GAP}%"
    rf"|{_OPERAND}{_GAP}{_INTERVAL_SEPARATOR}{_GAP}{_OPERAND})"
)

#: `0.85 ± 0.03`, `0.85 +/- 0.03`.
_PLUS_MINUS: Final = rf"{_OPERAND}{_GAP}(?:±|\+/-|\+-){_GAP}{_OPERAND}"

#: `< 0.001`, `<0.001`, `≤0.05`, `>= 3.5`. Longest operator first, or `>= 3.5` would be
#: read as `> = 3.5` and parse to nothing. The lookbehind rejects an arrow (`->`, `=>`)
#: and a doubled angle bracket, neither of which is a comparison.
#:
#: The name in front of a bound (`p`, `FDR`, `I²`) is deliberately **not** absorbed,
#: although `parse_value` would accept it. The name is the *metric*, a field `admit`
#: takes separately; inside the value's verbatim text it could name one quantity while
#: `Claim.metric` named another, with nothing to catch the disagreement. The cost is
#: measured and small: three bounds in the fixture corpus sit directly against a digit
#: (`I2<50`), where the gate's `_NUMBER_BEFORE` guard still reads the span as cutting a
#: number in half and refuses them as `partial_value` — a named refusal, not a wrong
#: claim.
_BOUND: Final = rf"(?<![-=<>])(?:<=|>=|≤|≥|<|>){_GAP}{_OPERAND}"

#: `12–15`, `220–223`. An en or em dash and no whitespace around it. `value.py` refuses
#: an ASCII hyphen because `12-15` is ambiguous against a signed value, and this module
#: keeps that decision rather than widening past what the parser can read. Tightness is
#: the second half: every one of the 66 dash ranges in the fixture corpus is written
#: tight, while a *spaced* em dash in a paper is prose punctuation (`in 2019 — 0.87`),
#: so requiring it costs nothing measured and removes the whole false-positive class.
#:
#: Exactly two numbers. The corpus contains `Accessed: 2025–12–18`, an ISO date whose
#: hyphens were typographically converted, and the first two of its three parts make a
#: perfectly well-formed `Range(2025, 12)` read out of a date. The guard runs at both
#: ends because rejecting only the leading pair leaves the scan to match the chain's
#: *trailing* pair instead, which is the same invention one number along. The `\d` in
#: the lookahead is load-bearing: without it the engine simply backtracks the high
#: endpoint from `12` to `1`, and `2025–1` satisfies a guard that only forbids a dash.
_RANGE: Final = rf"(?<![–—]){_OPERAND}[–—]{_OPERAND}(?![\d–—])"

#: `~10,000`, `≈ 100`.
_APPROXIMATE: Final = rf"[~∼≈≃]{_GAP}{_OPERAND}"

#: **ORDER IS THE CONTRACT**, and it is `value.py`'s order, most specific first, for
#: the same reason: tried the other way `12–15` is a `Point` that stopped reading after
#: `12`. Python's alternation takes the leftmost start and then the first branch that
#: matches there, so a composite always wins over the bare number inside it, and
#: `re.search` from the end of the previous match is what guarantees no piece of a
#: composite is ever emitted a second time on its own.
_VALUE: Final = re.compile(
    "|".join(
        (
            _INTERVAL_BRACKETED,
            _INTERVAL_MARKED,
            _PLUS_MINUS,
            _BOUND,
            _RANGE,
            _APPROXIMATE,
            _OPERAND,
        )
    )
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

    - `text` — the value exactly as written, verbatim, and whole: a bare number where
      the paper wrote one, and the entire notation where it wrote `p < 0.001` or
      `0.85 ± 0.03`. `span` reproduces it. Everything this module emits is something
      `parse_value` can read; nothing here decides what the value *means*.
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


def _is_a_quote_marker(text: str, start: int) -> bool:
    """Is the `>` at `start` a Markdown blockquote marker rather than a comparison?

    `> 97 patients were enrolled.` opening a line is a quotation, and reading it as
    `Bound(> 97)` would put a comparison in the record that the paper never made — the
    one failure mode this widening must not have. Only the line prefix is inspected,
    so the cost is a line rather than the document, and only for a `>`.
    """
    if text[start] != ">":
        return False
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[line_start:start]
    return prefix == "" or prefix.strip(" \t") == ""


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
    """Every value in `raw`, with context, in deterministic document order.

    One candidate per value the paper wrote, so a composite (`p < 0.001`, `12–15`) is
    one candidate and its pieces are not emitted beside it. The scan is
    non-overlapping by construction — each search resumes at the end of the last match
    — which is what makes that guarantee structural rather than a filtering pass.

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

    position = 0
    while (match := _VALUE.search(text, position)) is not None:
        if _is_a_quote_marker(text, match.start()):
            # Resume one character in, past the marker: the number it quotes is still
            # a number, and must still be found.
            position = match.start() + 1
            continue

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
        position = match.end()

    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                location_sort_key(candidate.span),
                candidate.text,
            ),
        )
    )
