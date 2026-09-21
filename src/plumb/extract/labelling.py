"""The blind labelling file: emitted empty, filled by a human, read back as the truth.

C1's selection rule — *which* of a paper's numbers are claims — has to be measured
against labels it did not author. If one author writes both the labels and the rule,
precision and recall measure "the code implements my rule" and cannot detect that the
rule itself is wrong; the metric comes back agreeing with itself whatever it says.
So the ordering is fixed (plan §0): the repository owner labels a blind set **first**,
those labels are committed, and only then is the rule written. This module emits the
file they label and reads the filled file back.

**The emitter never writes a value into the `label` column. Not a prediction, not a
default, not a "likely" hint, not a confidence.** This is the single load-bearing rule
of the file, and it is a guardrail rather than a detail: a pre-filled guess anchors the
labeller onto the very rule being measured — most people accept a plausible suggestion
— and the circularity the whole ordering exists to prevent walks back in through the
column meant to prevent it. The column is emitted present and `null`, and only a human
fills it. If a future change makes labelling "faster" by seeding the column, it has
destroyed the only measurement C1 has; `tests/extract/test_labelling.py` asserts the
column is empty for exactly that reason.

The same reasoning is why the loader refuses an unlabelled row instead of skipping it,
and why `LABELS` has two values and no `unsure`. A skipped row silently shrinks the
blind set and flatters whatever is scored against it; a third bucket would have to be
excluded from the denominator later, which is the same shrinkage with a friendlier
name.

**Format: JSONL, one row per line, and CSV was the rejected alternative.** The filled
file is committed evidence that the labels predate the rule, so it has to diff cleanly
in git and it has to carry real paper prose — contexts containing commas, quotation
marks, pipes, and line breaks. CSV round-trips those only by quoting, and an embedded
newline then makes one record span several physical lines: a single label changing
shows up as a multi-line hunk, and `git blame` on a row stops meaning anything. Worse,
CSV has dialects rather than a spec, and a spreadsheet opened over the file rewrites
quoting and line endings on save. JSON escapes a newline as `\\n`, so **one candidate
is always exactly one line**, `json` in the standard library is the only dialect, and
the escaping round-trips byte for byte. The cost is that the labeller edits JSON by
hand rather than in a spreadsheet — they edit one field at the end of each line, and
the loader refuses everything else they might disturb.

**What a row has to contain.** `Candidate.text` is a bare number: a labeller shown `12`
cannot tell 12% from a table index from a reference year, so the row must make the
number judgeable *without opening the paper*. It carries the surrounding sentence (or
table cell) split at the number itself — `context_before`, `text`, `context_after` —
which is both the exact context and its position within it. The split is why a sentence
containing four `12`s still shows the labeller which one this row is about, and it is
preferred to an offset (which a human cannot count) or to a separate marked-up copy of
the context (which duplicates the prose and can drift from it). The row also carries
the structural section hint and the source document, so a file merged from two papers
stays attributable per row.

**Table cells need two more columns, and they are derived here.** In prose the context
is a whole sentence and carries its own meaning. Inside a table the context *is* the
cell, so the row reads `0.840` and nothing else — the one place the sentence rule
leaves a labeller with nothing to judge. So a cell's row also carries `column_header`
(the row-0 cell of its column) and `row_label` (the column-0 cell of its row):
`Ours | AUC | 0.840` is judgeable where `0.840` is not. Both are `null` for a candidate
that is not in a table, and `null` for a cell in a column the author's header row never
declared — distinct from `""`, which is a header cell the author left empty. That is
the same `None`-is-not-`""` distinction `ordering.optional_sort_key` exists to keep.

They are derived from `parse_tables` here rather than added to `Candidate`, for two
reasons: `Candidate.context` is verbatim paper text and these are a lookup *about* it,
and the record shape freezes as hard as the tokenizer once labels exist against it — so
only what must be frozen is. The first labelling file will cover abstracts, where both
columns are empty throughout; they are built now because adding a column after labels
exist is exactly the change this ordering is meant to avoid.

This module emits no verdicts and makes no claim judgements. It formats a question for
a human and reads their answer back.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Final

from plumb.extract.candidates import SECTION_TABLE, Candidate
from plumb.extract.location import normalize_text
from plumb.extract.ordering import location_sort_key
from plumb.extract.tables import parse_tables

__all__ = [
    "LABELLING_FORMAT",
    "LABELS",
    "LABEL_CLAIM",
    "LABEL_NOT_CLAIM",
    "ROW_FIELDS",
    "LabelledCandidate",
    "LabellingError",
    "candidate_id",
    "emit_labelling_file",
    "load_labels",
]


#: The format tag on the header line. A file without it is not this file, and saying so
#: loudly beats reading someone's unrelated JSONL as a label set. Bumping it is how a
#: future field change announces itself to a loader holding an older file.
LABELLING_FORMAT: Final = "plumb.labelling.v1"

LABEL_CLAIM: Final = "claim"
LABEL_NOT_CLAIM: Final = "not-claim"

#: Closed, and two-valued on purpose — see the module docstring on `unsure`.
LABELS: Final = frozenset({LABEL_CLAIM, LABEL_NOT_CLAIM})

#: The row's fields, in the order they are written. Pinned because the file is
#: committed: reordering would rewrite every line of every labelling file in a diff for
#: no change in content. `label` is last so the column a human types in is at the end of
#: the line, where it is easy to find and hard to confuse with anything else.
ROW_FIELDS: Final = (
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

#: Domain separation, as `claim.py` and `hashing.py` do it: a labelling id must never
#: coincide with some other record's digest over the same strings.
_ID_SCHEME = b"plumb.labelling.id.v1"

#: Ids are truncated for readability — a 64-character digest per line is noise in a file
#: a human reads. 64 bits is ample for a paper's few thousand numbers, and the emitter
#: refuses a collision outright rather than trusting the arithmetic.
_ID_LENGTH: Final = 16

#: `sort_keys` is deliberately absent: key order is `ROW_FIELDS`, fixed by how each row
#: dict is built, so the human-facing order survives instead of being alphabetised.
#: Spaces after `:` and `,` because this file is read and edited by a person, unlike the
#: canonical claim document `serialize.py` writes.
_JSON: Final = {
    "ensure_ascii": False,
    "separators": (", ", ": "),
    "allow_nan": False,
}

_HEADER_INSTRUCTIONS: Final = (
    "Fill the `label` field of every row with one of label_values. Change nothing "
    "else. The label column is emitted empty on purpose: a suggested label would "
    "anchor the labeller and void the measurement these labels exist for."
)


class LabellingError(ValueError):
    """A labelling file that cannot be trusted as a label set, with the reason.

    A `ValueError` subclass so a caller that only knows it handed over bad data still
    catches it, and its own type so a caller that wants to report the line and the
    repair can tell it apart from any other bad value.
    """


@dataclass(frozen=True, slots=True)
class LabelledCandidate:
    """One candidate and the label a human gave it. Not a judgement of this package's.

    There is no `confidence` and no re-derived value here: this is a human's answer to
    "is this number a claim", recorded so a rule can later be scored against it. It is
    not a verdict, and nothing downstream may render it as one.
    """

    row_id: str
    candidate: Candidate
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.row_id, str):
            raise TypeError(
                "LabelledCandidate.row_id must be a string, got "
                f"{type(self.row_id).__name__}: {self.row_id!r}"
            )
        if not isinstance(self.candidate, Candidate):
            raise TypeError(
                "LabelledCandidate.candidate must be a Candidate, got "
                f"{type(self.candidate).__name__}: {self.candidate!r}"
            )
        if self.label not in LABELS:
            raise ValueError(
                f"unknown label {self.label!r}; the vocabulary is closed: "
                f"{sorted(LABELS)}"
            )


def _require_document(document: object) -> str:
    """The source document's name, checked before it reaches a committed file.

    An absolute path is refused rather than normalized: a labelling file is committed
    evidence, and a path from the labeller's machine is both noise in every diff and a
    needless disclosure of where they keep their papers. Normalizing it here would also
    mean reading the filesystem, which nothing in this package does.
    """
    if not isinstance(document, str):
        raise TypeError(
            "document must be a string naming the source document, got "
            f"{type(document).__name__}: {document!r}"
        )
    if not document:
        raise LabellingError(
            "document must name the source document; an unattributable row cannot be "
            "traced back to the paper it was read from"
        )
    if "\n" in document:
        raise LabellingError(
            f"document must be a single-line name, got {document!r}"
        )
    drive = len(document) > 1 and document[1] == ":" and document[0].isalpha()
    if document[0] in "/\\" or drive:
        raise LabellingError(
            f"document must be a repo-relative name, got the absolute path "
            f"{document!r}: this file is committed, and an absolute path pins it to "
            "one machine"
        )
    return document


def candidate_id(candidate: Candidate, *, document: str) -> str:
    """A stable id for one candidate in one document.

    Content-addressed rather than ordinal: a `c0007` would shift onto a different
    number the moment the paper gained a line, and every label committed against it
    would quietly point somewhere else. Derived from the document, the number and its
    span, so the same candidate in the same paper is always the same id, and the id is
    recomputable from the row — which is what lets the loader detect a row whose
    content was edited.

    The fields are encoded as one JSON array before hashing. That is the same
    unambiguity `claim.py` gets from length-prefixing — JSON is self-delimiting, so
    `["ab", "c"]` and `["a", "bc"]` cannot collapse to one byte string — reusing this
    module's own format rather than copying a second encoder into the package.
    """
    if not isinstance(candidate, Candidate):
        raise TypeError(
            f"expected a Candidate, got {type(candidate).__name__}: {candidate!r}"
        )
    parts = [
        _require_document(document),
        candidate.text,
        candidate.span.start,
        candidate.span.end,
    ]
    digest = hashlib.sha256(_ID_SCHEME)
    digest.update(json.dumps(parts, **_JSON).encode("utf-8"))
    return digest.hexdigest()[:_ID_LENGTH]


def _ordered(candidates: Iterable[Candidate]) -> tuple[Candidate, ...]:
    """Candidates in the one order this package sorts them in.

    The shared key from `ordering.py`, with the candidate text as the same total-making
    tie-breaker `extract_candidates` uses. Sorting here rather than trusting the caller
    is what makes "same candidates in, same bytes out" hold for a caller who built the
    set in some other order.
    """
    listed = list(candidates)
    for candidate in listed:
        if not isinstance(candidate, Candidate):
            raise TypeError(
                f"expected a Candidate, got {type(candidate).__name__}: {candidate!r}"
            )
    return tuple(
        sorted(listed, key=lambda item: (location_sort_key(item.span), item.text))
    )


def _context_start(candidate: Candidate, text: str, document: str) -> int:
    """Where this candidate's context begins in the normalized paper.

    `Candidate` carries the context string but not its offsets, and the number's
    position *within* the context is exactly what the row needs — a sentence with four
    `12`s is otherwise unlabellable. So the context is located in the paper: it is a
    verbatim substring of it (a stripped sentence, or a table cell whose span
    round-trips), and the occurrence that matters is one that actually encloses the
    candidate's span.

    Two refusals rather than a guess, because both mean the candidates did not come
    from this paper, and a row built from them would show a labeller a number the paper
    does not say there.

    If several enclosing occurrences exist — which needs a self-overlapping context,
    like `1 1` inside `1 1 1` — the first is taken. Any of them reconstructs the same
    context; the choice only moves where the split falls, and it is pinned so the bytes
    stay deterministic.
    """
    span = candidate.span
    if text[span.start : span.end] != candidate.text:
        raise LabellingError(
            f"candidate {candidate.text!r} does not appear in {document} at "
            f"[{span.start}, {span.end}): that span reads "
            f"{text[span.start : span.end]!r}. These candidates were not extracted "
            "from this paper."
        )
    context = candidate.context
    lowest = span.end - len(context)
    position = text.find(context, lowest if lowest > 0 else 0, span.start + len(context))
    while position >= 0:
        if position <= span.start and span.end <= position + len(context):
            return position
        position = text.find(context, position + 1, span.start + len(context))
    raise LabellingError(
        f"the context of {candidate.text!r} does not appear in {document} around "
        f"[{span.start}, {span.end}): {context!r}. These candidates were not "
        "extracted from this paper."
    )


#: One table cell's extent and the two labels that make it judgeable:
#: `(start, end, column_header, row_label)`.
_CellContext = tuple[int, int, str | None, str | None]


def _cell_contexts(text: str) -> tuple[_CellContext, ...]:
    """Every table cell in document order, with the header and label it sits under.

    `TableCell` already carries `row` and `column` — row 0 is the header and the
    delimiter row consumes no index — so the lookup is two dictionaries per table and
    no guessing about what a column means.

    `None` rather than `""` when the author's header row never declared this column: a
    data row may have more cells than its header (`tables.py` records what is written
    instead of padding), and "there is no header cell" is a different fact from "the
    header cell is empty".

    A row-0 cell is its own `column_header`, and a column-0 cell its own `row_label`.
    That falls out of the rule rather than being special-cased, and special-casing it
    would be this module deciding what a header *means*, which is the judgement the
    whole labelling step exists to leave to a human.
    """
    contexts: list[_CellContext] = []
    for table in parse_tables(text):
        headers = {cell.column: cell.text for cell in table.cells if cell.row == 0}
        labels = {cell.row: cell.text for cell in table.cells if cell.column == 0}
        contexts.extend(
            (
                cell.span.start,
                cell.span.end,
                headers.get(cell.column),
                labels.get(cell.row),
            )
            for cell in table.cells
        )
    return tuple(contexts)


def _canonical_rows(
    candidates: Iterable[Candidate], paper: str, document: str
) -> tuple[tuple[str, Candidate, dict[str, Any]], ...]:
    """The rows the emitter writes, as `(id, candidate, row)` in canonical order.

    Built in one place because both directions need it: the emitter serializes these,
    and the loader compares them field by field against what came back. That is what
    makes "only the label column may be edited" cover *every* column, including one
    added later — a loader with its own hand-written list of fields to check would
    quietly stop covering the next one.
    """
    if not isinstance(paper, str):
        raise TypeError(
            "the paper's text is required, not a path or raw bytes; got "
            f"{type(paper).__name__}: {paper!r}"
        )
    text = normalize_text(paper)
    cells = _cell_contexts(text)

    rows: list[tuple[str, Candidate, dict[str, Any]]] = []
    seen: dict[str, Candidate] = {}
    # Forward-only, like the scan in `candidates.py`: candidates and cells are both in
    # document order, so no cell is searched for twice.
    cursor = 0
    for candidate in _ordered(candidates):
        row_id = candidate_id(candidate, document=document)
        if row_id in seen:
            raise LabellingError(
                f"two candidates share the id {row_id!r}: {seen[row_id]!r} and "
                f"{candidate!r}. Ids are truncated digests; lengthen `_ID_LENGTH` "
                "rather than letting two candidates share one label."
            )
        seen[row_id] = candidate

        offset = candidate.span.start - _context_start(candidate, text, document)
        while cursor < len(cells) and cells[cursor][1] <= candidate.span.start:
            cursor += 1
        cell = (
            cells[cursor]
            if cursor < len(cells) and cells[cursor][0] <= candidate.span.start
            else None
        )
        in_table = candidate.section_hint == SECTION_TABLE
        # The section hint and the cell lookup are two readings of the same structure.
        # If they ever disagree, one of them is placing numbers in columns the author
        # did not write, and a labeller would read a header belonging to another row.
        if in_table and cell is None:
            raise LabellingError(
                f"candidate {candidate.text!r} at [{candidate.span.start}, "
                f"{candidate.span.end}) is marked as a table cell but its span is "
                "not in a table cell of this paper"
            )
        if cell is not None and not in_table:
            raise LabellingError(
                f"candidate {candidate.text!r} at [{candidate.span.start}, "
                f"{candidate.span.end}) sits in a table cell but is not marked as "
                f"one: its section hint is {candidate.section_hint!r}"
            )

        rows.append(
            (
                row_id,
                candidate,
                {
                    "id": row_id,
                    "document": document,
                    "section": candidate.section_hint,
                    "column_header": cell[2] if cell is not None else None,
                    "row_label": cell[3] if cell is not None else None,
                    "text": candidate.text,
                    "span": [candidate.span.start, candidate.span.end],
                    "context_before": candidate.context[:offset],
                    "context_after": candidate.context[offset + len(candidate.text) :],
                    # Empty, always. A value here is the circularity this module is
                    # built to prevent — see the module docstring.
                    "label": None,
                },
            )
        )
    return tuple(rows)


def _header_line() -> str:
    """The first line: what this file is, and what the labeller may write in it.

    Carries no timestamp, no path and no count — nothing that would change between two
    emissions of the same candidates.
    """
    return json.dumps(
        {
            "format": LABELLING_FORMAT,
            "label_values": sorted(LABELS),
            "instructions": _HEADER_INSTRUCTIONS,
        },
        **_JSON,
    )


def emit_labelling_file(
    candidates: Iterable[Candidate], *, paper: str, document: str
) -> bytes:
    """The labelling file for `candidates`, with every label column empty.

    `paper` is the text the candidates were extracted from. It is needed twice over: to
    place each number within its own context (`_context_start`) and to read a table
    cell's header and row label off the parsed table (`_cell_contexts`). Checking the
    candidates against it means a mismatched pair fails here rather than producing a
    file that quietly misquotes the paper.

    Returns `bytes` for the reason `serialize.py` does: "byte-identical" is only
    assertable on bytes, and a `str` leaves the encoding unpinned.

    **Nothing in here writes a label.** See the module docstring; this is the rule the
    module exists to hold.
    """
    name = _require_document(document)
    lines = [_header_line()]
    lines.extend(
        json.dumps(row, **_JSON)
        for _, _, row in _canonical_rows(candidates, paper, name)
    )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _object(line: str, number: int) -> dict[str, Any]:
    """One line parsed as a JSON object, or a failure naming the line."""
    try:
        parsed = json.loads(line)
    except ValueError as error:
        raise LabellingError(
            f"line {number}: not valid JSON ({error}). Every line of a labelling file "
            "is one JSON object; a context containing a newline is escaped, never "
            "wrapped onto a second line."
        ) from error
    if not isinstance(parsed, dict):
        raise LabellingError(
            f"line {number}: expected a JSON object, got {type(parsed).__name__}"
        )
    return parsed


def _check_header(line: str) -> None:
    parsed = _object(line, 1)
    if parsed.get("format") != LABELLING_FORMAT:
        raise LabellingError(
            f"line 1: not a {LABELLING_FORMAT} labelling file — its first line must be "
            f"the header carrying {'format'!r}: {LABELLING_FORMAT!r}, got "
            f"{parsed.get('format')!r}"
        )


def _check_fields(row: dict[str, Any], number: int) -> None:
    missing = [field for field in ROW_FIELDS if field not in row]
    if missing:
        raise LabellingError(
            f"line {number}: missing field(s) {missing}; a labelling row carries "
            f"exactly {list(ROW_FIELDS)}"
        )
    unexpected = [field for field in row if field not in ROW_FIELDS]
    if unexpected:
        raise LabellingError(
            f"line {number}: unexpected field(s) {unexpected}; a labelling row carries "
            f"exactly {list(ROW_FIELDS)}. A column of predictions beside the labels is "
            "the anchoring this file is shaped to prevent."
        )


def _read_label(row: dict[str, Any], number: int, row_id: object) -> str:
    """The row's label, or a refusal. Never a default, never a skip."""
    label = row["label"]
    if label is None:
        raise LabellingError(
            f"line {number}: row {row_id!r} has no label. Every candidate must be "
            f"labelled {sorted(LABELS)} before the file is a label set — an unlabelled "
            "row cannot be scored, and guessing one is the circularity these labels "
            "exist to rule out."
        )
    if not isinstance(label, str) or isinstance(label, bool) or label not in LABELS:
        raise LabellingError(
            f"line {number}: row {row_id!r} has an unparseable label {label!r}; the "
            f"vocabulary is closed: {sorted(LABELS)}"
        )
    return label


def _check_unedited(
    row: dict[str, Any], number: int, row_id: str, canonical: dict[str, Any]
) -> None:
    """Every column but `label` must still say what the emitter wrote.

    Compared against the emitter's own row rather than a hand-written list of fields,
    so a column added later is covered without anyone remembering to add it here. The
    labeller edits one field; anything else differing means the row no longer describes
    the candidate it names — a reworded context, or a header lifted from another
    column, is a label given to something the paper does not say, and it would enter
    the blind set looking exactly like a good one.
    """
    for field in ROW_FIELDS:
        if field == "label":
            continue
        if row[field] != canonical[field]:
            raise LabellingError(
                f"line {number}: row {row_id!r} no longer matches the candidate it "
                f"names — {field} is {row[field]!r}, expected {canonical[field]!r}. "
                "Only the label column may be edited."
            )


def load_labels(
    data: bytes, *, candidates: Iterable[Candidate], paper: str, document: str
) -> tuple[LabelledCandidate, ...]:
    """The filled file, read back as the blind label set for `candidates`.

    Every failure is loud and names the line: a hand-filled file goes wrong in ordinary
    ways, and a loader that shrugged — skipping the blank row, coercing the typo,
    ignoring the id it did not recognise — would hand back a smaller or wrong label set
    that still scores fine.

    `paper` is the same text the candidates were extracted from. The loader re-derives
    the rows the emitter would have written and compares, which is the only way the
    "only the label column may be edited" check can cover the columns that are derived
    from the paper's tables rather than carried on `Candidate`.

    The result is in the candidates' own canonical order, not the file's, so a file
    whose lines were reordered by an editor still loads identically.
    """
    if not isinstance(data, bytes):
        raise TypeError(
            "load_labels takes the file's bytes, not text; a decoding decided at the "
            f"call site is an encoding nobody pinned. Got {type(data).__name__}"
        )
    name = _require_document(document)
    expected = {
        row_id: (candidate, row)
        for row_id, candidate, row in _canonical_rows(candidates, paper, name)
    }

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise LabellingError(
            f"a labelling file must be UTF-8, as it was emitted: {error}"
        ) from error

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise LabellingError(
            f"empty file: a {LABELLING_FORMAT} labelling file begins with its header "
            "line"
        )
    _check_header(lines[0])

    found: dict[str, tuple[int, str]] = {}
    for offset, line in enumerate(lines[1:]):
        number = offset + 2
        row = _object(line, number)
        _check_fields(row, number)
        row_id = row["id"]
        if not isinstance(row_id, str) or row_id not in expected:
            raise LabellingError(
                f"line {number}: unknown row id {row_id!r} — no candidate extracted "
                f"from {name} has it. Either the file was emitted from a different "
                "paper or document name, or the paper changed since it was emitted; "
                "re-emit rather than re-point the labels."
            )
        if row_id in found:
            raise LabellingError(
                f"line {number}: duplicate row id {row_id!r}, first labelled on line "
                f"{found[row_id][0]}"
            )
        _check_unedited(row, number, row_id, expected[row_id][1])
        found[row_id] = (number, _read_label(row, number, row_id))

    unlabelled = [row_id for row_id in expected if row_id not in found]
    if unlabelled:
        raise LabellingError(
            f"the file does not label every candidate: {len(unlabelled)} of "
            f"{len(expected)} missing, beginning with {unlabelled[:3]}. A blind set "
            "with rows quietly dropped is a smaller denominator, not a passing score."
        )

    return tuple(
        LabelledCandidate(
            row_id=row_id, candidate=candidate, label=found[row_id][1]
        )
        for row_id, (candidate, _) in expected.items()
    )
