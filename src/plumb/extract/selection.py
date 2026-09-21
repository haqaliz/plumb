"""The claim-selection rule (M3): which candidates are worth admitting.

The gate (`admit.py`) checks that a candidate is *grounded*; this module checks that
it is *worth* admitting — asserted by this paper about its own results, carrying a
named metric, and sitting in abstract/results/table (plan D1). It is the substance of
C1 (`CAPABILITY_ROADMAP.md:42`) and is scored against labels it did not author
(`labelling.py`, plan M15).

Two structural choices are the point of the module:

**Selection causes are a separate closed vocabulary.** The gate's `NON_CLAIM_CAUSES`
describe grounding and notation failures (`ungrounded`, `partial_value`, ...); these
describe worth failures (`year`, `reference_numeral`, `related_work`, ...). The two
sets never intersect (plan D2): a cause spelled like a verdict would be read as one,
and a selection-side refusal must never look like a gate-side one — C5 wants to tell
them apart.

**The rule decides *before* the gate.** Reference numerals, years and the like are
kept "from reaching the gate at all" (test_admit.py:992-994); `admit` is unchanged
and `TestTheGateIsNotTheSelectionRule` still passes. The rule's rejections surface
as `SelectionRejection` — never a `Claim`, never a verdict, never silent (parent M4).

The rejection cues below are CLOSED, deterministic lists — provisional by design,
measured by the blind score (plan §7). They err toward a false negative over a false
claim: the documented safe direction (`extraction-core/spec.md:87-90`).

**The sample-size fall-through class dies here, structurally.** `n of 412`, a table
cell `| n | 412 |` and friends are refused by the named-metric requirement — `n`
supplies no metric — never by enumerating spellings (spec.md:73-90). The gate's
`study_parameter` refusal and `study_parameters(raw)` are not re-implemented here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Final, Iterable

from plumb.extract.candidates import (
    SECTION_OTHER,
    SECTION_REFERENCES,
    Candidate,
)
from plumb.extract.location import Location

__all__ = [
    "CAUSE_AXIS_LABEL",
    "CAUSE_DOI_DIGITS",
    "CAUSE_FIGURE_NUMBER",
    "CAUSE_HYPERPARAMETER",
    "CAUSE_NO_NAMED_METRIC",
    "CAUSE_OUTSIDE_SECTIONS",
    "CAUSE_REFERENCE_NUMERAL",
    "CAUSE_RELATED_WORK",
    "CAUSE_VERSION_STRING",
    "CAUSE_YEAR",
    "SELECTION_CAUSES",
    "Selected",
    "SelectionRejection",
    "metric_of",
    "select",
]

# --- the closed selection-side cause vocabulary -------------------------------

CAUSE_REFERENCE_NUMERAL: Final = "reference_numeral"
CAUSE_OUTSIDE_SECTIONS: Final = "outside_sections"
CAUSE_YEAR: Final = "year"
CAUSE_FIGURE_NUMBER: Final = "figure_number"
CAUSE_VERSION_STRING: Final = "version_string"
CAUSE_DOI_DIGITS: Final = "doi_digits"
CAUSE_HYPERPARAMETER: Final = "hyperparameter"
CAUSE_AXIS_LABEL: Final = "axis_label"
CAUSE_RELATED_WORK: Final = "related_work"
CAUSE_NO_NAMED_METRIC: Final = "no_named_metric"

SELECTION_CAUSES: Final = frozenset(
    {
        CAUSE_REFERENCE_NUMERAL,
        CAUSE_OUTSIDE_SECTIONS,
        CAUSE_YEAR,
        CAUSE_FIGURE_NUMBER,
        CAUSE_VERSION_STRING,
        CAUSE_DOI_DIGITS,
        CAUSE_HYPERPARAMETER,
        CAUSE_AXIS_LABEL,
        CAUSE_RELATED_WORK,
        CAUSE_NO_NAMED_METRIC,
    }
)


@dataclass(frozen=True, slots=True)
class SelectionRejection:
    """A candidate the rule refused, with the cause, text and location preserved.

    Shape mirrors `NonClaim` (admit.py) so downstream consumers see one surface;
    the cause vocabulary is deliberately disjoint from the gate's.
    """

    cause: str
    text: str
    location: Location

    def __post_init__(self) -> None:
        if not isinstance(self.cause, str):
            raise TypeError(
                f"SelectionRejection.cause must be a string, got "
                f"{type(self.cause).__name__}: {self.cause!r}"
            )
        if self.cause not in SELECTION_CAUSES:
            raise ValueError(
                f"unknown selection cause {self.cause!r}; the vocabulary is "
                f"{sorted(SELECTION_CAUSES)}"
            )
        if not isinstance(self.text, str):
            raise TypeError(
                f"SelectionRejection.text must be a string, got "
                f"{type(self.text).__name__}: {self.text!r}"
            )
        if not isinstance(self.location, Location):
            raise TypeError(
                "SelectionRejection.location must be a Location, got "
                f"{type(self.location).__name__}: {self.location!r}"
            )


@dataclass(frozen=True, slots=True)
class Selected:
    """A candidate that passed the rule, with the metric the gate needs.

    `metric` is the free-text quantity phrase from the paper's own context (plan
    D3) — the named quantity C4 will aim a locator at; `units` is a best-effort
    token read after the value from a closed list, never guessed (plan D4).
    """

    candidate: Candidate
    metric: str
    units: str | None = None


# --- deterministic cue lists (closed, provisional, documented) ---------------

#: Operator characters that can end a quantity phrase inside the candidate text
#: itself (`95% CI: 0.4%-1.7%` -> "95% CI", `p < 0.001` -> "p"). `%` is not one —
#: it is a unit, and `-` is not one — it is ambiguous against a signed value.
_METRIC_OPERATORS: Final = ("=", "<", ">", "≤", "≥", "±", "≈", "~", ":")

#: Clause boundaries: the metric phrase is the text between the candidate and the
#: last of these, falling back leftward until something non-empty remains.
_BOUNDARIES: Final = (";", ":", ",", "(", "[")

#: Trailing words stripped from a metric phrase, repeatedly. Function words and
#: hedges; never a quantity name.
_TRAILING_WORDS: Final = frozenset(
    {
        "is", "was", "were", "are", "be", "been", "of", "for", "in", "by",
        "with", "at", "the", "a", "an", "and", "or", "to", "from", "between",
        "since", "during", "approximately", "about", "around", "roughly",
        "vs", "versus",
    }
)

#: Leading words stripped from a metric phrase: determiners and subject pronouns.
_LEADING_WORDS: Final = frozenset(
    {"the", "a", "an", "we", "our", "their", "this", "these", "those", "and",
     "as", "in", "for", "of", "to", "at", "by", "that"}
)

#: Quantity names that are NOT result metrics: sample sizes, participant groups,
#: design metadata. A metric ending in any of these (word-boundary, multi-word
#: entries included) is `no_named_metric` — this is what closes the sample-size
#: fall-through class structurally (spec.md:73-90).
_N_TOKENS: Final = frozenset(
    {
        "n", "sample size", "sample sizes", "sample", "samples",
        "participant", "participants", "patient", "patients",
        "subject", "subjects", "case", "cases", "study", "studies",
        "cohort", "cohorts", "group", "groups",
        "male", "males", "female", "females",
        "measurement", "measurements", "linear", "angular",
        "dimension", "dimensions", "landmark", "landmarks",
        "predictor", "predictors", "indicator", "indicators",
        "model", "models", "million", "type",
        "epoch", "epochs", "iteration", "iterations",
    }
)

#: Single verbs that announce a subject count rather than a result ("study
#: included 120", "we recorded 22"). Deliberately excludes result verbs
#: ("increased", "improved") which legitimately precede a claim.
_SUBJECT_VERBS: Final = frozenset(
    {
        "included", "involved", "recruited", "enrolled", "comprised",
        "comprising", "consisted", "consisting", "conducted", "performed",
        "collected", "recorded", "analyzed", "analysed", "examined", "used",
    }
)

#: Units read from the token after the value; never guessed (plan D4).
_UNITS: Final = frozenset(
    {"%", "kg", "g", "mg", "μg", "µg", "ml", "mL", "mm", "cm", "ms", "s",
     "Hz", "IU", "ng", "nM", "µM"}
)

#: Immediate-context windows: cues must live near the candidate. A window over
#: the whole sentence would let a cue from another clause reject a legit value
#: ("...previously reported algorithm (Brier 0.049 vs 0.061; AUC 0.84 ...)" —
#: "reported" is 80 characters from 0.84, and "vs" of the *previous* pair is 11).
_VS_WINDOW: Final = 8
_CUE_WINDOW: Final = 24

_YEAR_RE: Final = re.compile(r"^\d{4}$")
_YEAR_CUES: Final = re.compile(r"\b(in|between|from|since|during|to)\b|[\(–—]", re.IGNORECASE)
_FIGURE_CUES: Final = re.compile(
    r"\b(fig(?:ure)?s?\.?|table|page|pp\.?|eq(?:uation)?s?\.?|suppl(?:ementary)?)\b",
    re.IGNORECASE,
)
_VERSION_MANY_DOTS: Final = re.compile(r"^(>=|<=|>|<|=|≈|~)?\s*\d+(\.\d+){2,}$")
_VERSION_SOME_DOTS: Final = re.compile(r"^(>=|<=|>|<|=)?\s*\d+(\.\d+)+$")
_VERSION_CUES: Final = re.compile(r"\b(version|release|build|python)\b|\br\b", re.IGNORECASE)
_DOI_RE: Final = re.compile(r"\b10\.\d{4,}/|\bdoi[:.]|\borcid\b|\bgrant\b", re.IGNORECASE)
_HYPERPARAM_CUES: Final = re.compile(
    r"\b(learning rate|batch size|epochs?|dropout|kernel size|window size|"
    r"hidden unit|seed|lr)\b",
    re.IGNORECASE,
)
_AXIS_CUES: Final = re.compile(r"\b(x-?axis|y-?axis|tick|scale)\b", re.IGNORECASE)
_CITATION_BRACKET: Final = re.compile(r"^[\[\(]")
#: Numerals-and-separators only: a decimal point makes it a value, not a citation
#: run (`[30,31]` is a citation; `(0.226)` is a number in parentheses).
_CITATION_CONTENT: Final = re.compile(r"^[\d\s,;–-]+$")
_RELATED_WORK_CUES: Final = re.compile(
    r"\b(reported|found|showed|observed|estimated|previous|prior|"
    r"study by|according to|performed by)\b",
    re.IGNORECASE,
)
_RELATED_WORK_VS: Final = re.compile(r"\b(vs|versus)\s*$", re.IGNORECASE)
_ET_AL: Final = re.compile(r"\bet al\b", re.IGNORECASE)
_SURNAME_YEAR: Final = re.compile(r"\([A-Z][A-Za-z' -]{1,30},\s*(?:19|20)\d{2}\)")
_NUMBER_TAIL: Final = re.compile(r"[0-9][0-9.,%×]*$")
_AFTER_TOKEN: Final = re.compile(r"^[^A-Za-z0-9]*([A-Za-zµμ]+)")

#: The check order — the contract. Section first (structural), then the lexical
#: categories in this exact order, then the metric. A candidate matching two
#: categories carries the documented first cause (tested).
#:   references -> reference_numeral; other -> outside_sections
#:   year -> figure_number -> version_string -> doi_digits -> hyperparameter
#:     -> axis_label -> reference_numeral(citation) -> related_work
#:   metric_of empty -> no_named_metric


def _position(candidate: Candidate, normalized_text: str) -> int:
    """The candidate's offset within its own `context`.

    `candidate.span` indexes the normalized paper; the rule needs the candidate's
    position inside the sentence. The sentence's own start is recovered by finding
    it in the paper — `context.index(text)` alone is wrong when the candidate's
    text occurs earlier in the sentence (real case: `A2, A3, A5, A10, A28` — the
    first `5` is the predictor count, not `A5`).
    """
    context = candidate.context
    context_start = normalized_text.find(context)
    if context_start >= 0 and candidate.span.start >= context_start:
        relative = candidate.span.start - context_start
        if relative + len(candidate.text) <= len(context):
            return relative
    return context.index(candidate.text)


def _window(context: str, position: int, width: int) -> str:
    return context[max(0, position - width):position]


_NUMBER_RUN: Final = re.compile(r"\d[\d.,%×]*")


def _preceding_clauses(context: str, position: int) -> list[str]:
    """Clauses before the candidate, cut at boundaries, rightmost first.

    The metric phrase is the clause immediately before the value; when that is
    empty (a number opens a parenthetical, e.g. `prediction interval (0.03%`),
    the chain falls back leftward to the previous boundary. A previous *number*
    is a boundary too: a metric phrase never spans another value
    (`The sensitivity was 0.87 and the specificity 0.92` — the phrase for `0.92`
    is `and the specificity`, not the whole sentence).
    """
    head = context[:position]
    cuts = [i for i, char in enumerate(head) if char in _BOUNDARIES]
    cuts.extend(match.end() for match in _NUMBER_RUN.finditer(head))
    cuts = sorted(set(cuts))
    clauses: list[str] = []
    previous = 0
    for cut in cuts:
        clauses.append(head[previous:cut])
        previous = cut + 1
    clauses.append(head[previous:])
    clauses.reverse()
    return clauses


def _clean(phrase: str) -> str | None:
    """Strip noise from a metric phrase until stable; `None` if nothing remains."""
    text = phrase.strip()
    while True:
        before = text
        text = re.sub(r"^[=<>≤≥±≈~:\(\[\),%]+", "", text).strip()
        text = re.sub(r"[=<>≤≥±≈~:\(\[\),;%\-]+$", "", text).strip()
        words = text.split()
        if words and words[-1].lower() in _TRAILING_WORDS:
            text = " ".join(words[:-1]).strip()
        text = _NUMBER_TAIL.sub("", text).strip()
        words = text.split()
        if words and words[0].lower() in _LEADING_WORDS:
            text = " ".join(words[1:]).strip()
        if text == before:
            break
    if not text:
        return None
    return " ".join(text.split())


def _ends_with_n_token(metric: str) -> bool:
    lowered = metric.lower()
    return any(
        lowered == token or lowered.endswith(" " + token)
        for token in _N_TOKENS
    )


def _after_word(context: str, end: int) -> str | None:
    """The first word after the candidate (its end offset `end`), lowercased."""
    match = _AFTER_TOKEN.match(context[end:])
    if match is None:
        return None
    return match.group(1).lower()


def _directly_preceded_by_a_letter(candidate: Candidate, normalized_text: str) -> bool:
    start = candidate.span.start
    if start <= 0:
        return False
    return normalized_text[start - 1].isalpha()


def _is_bracketed_citation(context: str, position: int) -> bool:
    """A bracket-enclosed numeral run like `[30,31]` — a citation, not a value.

    Adjacent brackets only (1 char): a parenthetical like `(Brier 0.049` opens
    before a *word*, not before the number. The content between the brackets must
    be numerals and separators only — `(0.03%-17.3%)` carries a unit and is an
    interval, not a citation.
    """
    before = context[max(0, position - 1):position]
    if not _CITATION_BRACKET.match(before):
        return False
    opener = "[" if before == "[" else "("
    closer = "]" if opener == "[" else ")"
    rest = context[position + 1:]
    close = rest.find(closer)
    if close < 0 or close > 12:
        return False
    content = context[position - 1:position + 1 + close + 1]
    inner = content[1:-1]
    return bool(_CITATION_CONTENT.match(inner))


def metric_of(candidate: Candidate, *, normalized_text: str) -> str | None:
    """The free-text quantity phrase for a candidate, or `None` when it has none.

    Two deterministic paths (plan D3):
    1. A quantity phrase *inside* the candidate text, before the first metric
       operator — `95% CI: 0.4%-1.7%` -> `95% CI`, `p < 0.001` -> `p`. The phrase
       must contain a letter or `%`: a bare number head (`0.85 ± 0.03`) is a
       value, not a name.
    2. The clause immediately before the value, cut at the last clause boundary
       and falling back leftward — `The sensitivity was 0.87` -> `sensitivity`.
    The result is rejected as no-metric when it names only a sample-size or
    subject category (`n`, `sample size`, `participants`, ...), when it is a
    subject-counting verb (`included`), when the number is a direct component of
    an identifier (`R2`, `A28` — a letter directly before the digit), or when
    nothing survives the noise stripping.
    """
    position = _position(candidate, normalized_text)
    context = candidate.context

    for operator in _METRIC_OPERATORS:
        if operator in candidate.text:
            head, _, _ = candidate.text.partition(operator)
            head = head.strip()
            if head and any(char.isalpha() or char == "%" for char in head):
                named = _clean(head)
                if named is not None:
                    return named
            break

    for clause in _preceding_clauses(context, position):
        named = _clean(clause)
        if named is None:
            continue
        after = _after_word(context, position + len(candidate.text))
        if _ends_with_n_token(named):
            return None
        last = named.split()[-1].lower()
        if last in _SUBJECT_VERBS:
            return None
        if after is not None and after in _N_TOKENS:
            return None
        if _directly_preceded_by_a_letter(candidate, normalized_text):
            return None
        return named
    return None


def _units_token(candidate: Candidate, normalized_text: str) -> str | None:
    position = _position(candidate, normalized_text)
    after = _after_word(candidate.context, position + len(candidate.text))
    if after is not None and after in _UNITS:
        return after
    return None


def _reject(cause: str, candidate: Candidate) -> SelectionRejection:
    return SelectionRejection(
        cause=cause, text=candidate.text, location=candidate.span
    )


def select(
    candidate: Candidate,
    *,
    normalized_text: str,
) -> Selected | SelectionRejection:
    """The rule: does this candidate deserve to reach the gate?

    `normalized_text` is the same normalized paper the candidate's span indexes —
    needed to locate the candidate inside its sentence and to test adjacency
    (a sentence can contain the same digits twice, and an identifier like `A28`
    is only visible from the surrounding letters).
    """
    position = _position(candidate, normalized_text)
    context = candidate.context

    if candidate.section_hint == SECTION_REFERENCES:
        return _reject(CAUSE_REFERENCE_NUMERAL, candidate)
    if candidate.section_hint == SECTION_OTHER:
        return _reject(CAUSE_OUTSIDE_SECTIONS, candidate)

    if _YEAR_RE.match(candidate.text) and 1900 <= int(candidate.text) <= 2100:
        if _YEAR_CUES.search(_window(context, position, _CUE_WINDOW)):
            return _reject(CAUSE_YEAR, candidate)

    if _FIGURE_CUES.search(_window(context, position, _CUE_WINDOW)):
        return _reject(CAUSE_FIGURE_NUMBER, candidate)

    if _VERSION_MANY_DOTS.match(candidate.text) or (
        _VERSION_CUES.search(_window(context, position, _CUE_WINDOW))
        and _VERSION_SOME_DOTS.match(candidate.text)
    ):
        return _reject(CAUSE_VERSION_STRING, candidate)

    if _DOI_RE.search(context):
        return _reject(CAUSE_DOI_DIGITS, candidate)

    if _HYPERPARAM_CUES.search(_window(context, position, _CUE_WINDOW)):
        return _reject(CAUSE_HYPERPARAMETER, candidate)

    if _AXIS_CUES.search(_window(context, position, _CUE_WINDOW)):
        return _reject(CAUSE_AXIS_LABEL, candidate)

    if _is_bracketed_citation(context, position):
        return _reject(CAUSE_REFERENCE_NUMERAL, candidate)

    if _RELATED_WORK_VS.search(_window(context, position, _VS_WINDOW)) or (
        _RELATED_WORK_CUES.search(_window(context, position, _CUE_WINDOW))
    ) or _ET_AL.search(context) or _SURNAME_YEAR.search(context):
        return _reject(CAUSE_RELATED_WORK, candidate)

    metric = metric_of(candidate, normalized_text=normalized_text)
    if metric is None:
        return _reject(CAUSE_NO_NAMED_METRIC, candidate)

    return Selected(
        candidate=candidate,
        metric=metric,
        units=_units_token(candidate, normalized_text),
    )