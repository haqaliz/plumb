"""The admission gate: the only door a `Claim` comes through, and the refusals it emits.

A candidate is a number somebody noticed. A `Claim` is an assertion this paper made,
pinned to the place it made it. Turning the first into the second is the one decision
in C1 that may never be taken on trust, so it is taken here and nowhere else.

**One door (plan D1).** No other module in this package constructs a `Claim`, and
`tests/extract/test_admit.py` parses the package to prove it. The BYOK LLM proposer is
out of scope, but the seam it will plug into is built now: a proposer arriving to find
the deterministic core already constructing records directly would have a second path
to a `Claim` that skips grounding entirely — a model's opinion reaching the verdict
layer as though it had been checked (`ARCHITECTURE.md:59-61`, `CLAUDE.md` #4). A
proposer may *propose* a candidate and a metric; it comes through this function like
everything else, and the paper decides.

**Grounding is the evidence, and it is re-checked rather than trusted.** The invariant
is one line, and the rest of this module exists to hold it:

    normalized_text[claim.location.start:claim.location.end] == claim.reported_value.text

Four things break it, and all four are refused rather than repaired: a span that has
moved, a span that runs off the end of the paper (Python slicing clamps, so that one
*looks* like it round-trips), a zero-width span (which matches every paper ever
written), and a span padded with whitespace (which would quote ` 0.87` for the value
`0.87`).

**Refusal is a record (plan D2, M4).** Every candidate that does not become a `Claim`
becomes a `NonClaim` with a named cause. Never `None`, never a silent skip: a silent
drop is indistinguishable from a claim that was never there, and it flatters the
coverage number the Phase 0 gate rests on. The vocabulary is closed, and it is
**extraction-side** — it borrows nothing from C4. This layer runs nothing, so it has no
standing to say `REPRODUCED` or `UNVERIFIED` about anything; a cause spelled like a
verdict would be read downstream as one.

**This is not selection.** Which numbers are worth admitting — abstract and results
only, no years, no version strings, no reference numerals — is M3, deferred to part 2
so it can be scored against labels it did not author. The gate takes whatever it is
handed and checks it. It reads `Candidate.section_hint` not at all.

This module emits no verdicts.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final

from plumb.extract.candidates import Candidate, extract_candidates
from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, Location, normalize_text
from plumb.extract.ordering import location_sort_key
from plumb.extract.study import StudyParameter
from plumb.extract.value import parse_value

__all__ = [
    "CAUSE_PARTIAL_VALUE",
    "CAUSE_STUDY_PARAMETER",
    "CAUSE_UNGROUNDED",
    "CAUSE_UNNAMED_METRIC",
    "CAUSE_UNPARSED_VALUE",
    "NON_CLAIM_CAUSES",
    "NonClaim",
    "admit",
    "study_parameters",
]


# --------------------------------------------------------------------------------
# The cause vocabulary
# --------------------------------------------------------------------------------

#: The span no longer yields this text in this paper — it has moved, it runs past the
#: end, it is zero-width, or it addresses surrounding whitespace as well as the value.
#: Nothing downstream can check a claim whose location does not reproduce it.
CAUSE_UNGROUNDED: Final = "ungrounded"

#: The span covers part of a value the paper wrote as a whole: the `0.001` of
#: `p < 0.001`, the `0.03` of `0.85 ± 0.03`, an endpoint of `12–15%`. Admitting the
#: fragment on its own would record `p = 0.001` — a claim the paper never made, against
#: which a re-derived `0.0009` would look like a contradiction. The caller's remedy is
#: to widen the candidate over the notation as written; see `_is_a_fragment`.
CAUSE_PARTIAL_VALUE: Final = "partial_value"

#: The number is a reported sample size, which is study metadata rather than a result
#: (see `study.py`). It is extracted — C7 needs it — as a `StudyParameter`, through
#: `study_parameters`, and never as a `Claim`.
CAUSE_STUDY_PARAMETER: Final = "study_parameter"

#: No named quantity was given. C4 binds a claim by aiming a locator at a *named*
#: quantity; with no name a later stage would have to re-interpret the surrounding
#: prose, which is the guessing this project does not do.
CAUSE_UNNAMED_METRIC: Final = "unnamed_metric"

#: The text grounded, but `parse_value` could not read a value out of it. Aspect 1
#: states that `parse_value` returning `None` is the caller-decides seam for M4; this
#: is that decision, recorded rather than raised.
CAUSE_UNPARSED_VALUE: Final = "unparsed_value"

#: Closed, and deliberately disjoint from C4's verdict vocabulary. A cause reaches the
#: discrepancy corpus and the labelling file; an invented one would arrive there
#: looking like an established fact about the paper, and a verdict-shaped one would
#: arrive looking like a judgement this layer has no standing to make.
NON_CLAIM_CAUSES: Final = frozenset(
    {
        CAUSE_UNGROUNDED,
        CAUSE_PARTIAL_VALUE,
        CAUSE_STUDY_PARAMETER,
        CAUSE_UNNAMED_METRIC,
        CAUSE_UNPARSED_VALUE,
    }
)


@dataclass(frozen=True, slots=True)
class NonClaim:
    """A candidate that did not become a claim, and why.

    Deliberately **not** a `Claim` and not substitutable for one: no shared base beyond
    `object`, mirroring how `StudyParameter` is kept separate. A common ancestor, even
    an empty marker one, is how the distinction erodes — a later stage types against
    the base and starts accepting refusals wherever it meant claims, and a refusal
    counted as a claim is an item in the coverage denominator that can never bind.

    Three fields, and the absences matter as much:

    - `cause` — one of `NON_CLAIM_CAUSES`. Machine-readable, so triage can count
      causes rather than parse sentences.
    - `text` — what was refused, verbatim.
    - `location` — where it was, so a human can go and look. Recorded even for an
      `ungrounded` refusal, where the span is the very thing in question: it is the
      only handle on what went wrong.

    **There is no `confidence`,** for the reason `Claim` has none: a confidence float
    becomes a model's opinion standing in for a re-derived value (`CLAUDE.md` #1).
    **There is no `id`.** `Claim` derives one because aspect 3 requires mentions of one
    result to merge under a stable identity; no equivalent requirement has been stated
    for refusals, and deriving a hash here would make it look as though the question of
    whether two refusals are the same refusal had already been settled. **There is no
    `verdict`,** because this aspect runs nothing.
    """

    cause: str
    text: str
    location: Location

    def __post_init__(self) -> None:
        if not isinstance(self.cause, str):
            raise TypeError(
                f"NonClaim.cause must be a string, got {type(self.cause).__name__}: "
                f"{self.cause!r}"
            )
        if self.cause not in NON_CLAIM_CAUSES:
            raise ValueError(
                f"unknown non-claim cause {self.cause!r}; the vocabulary is closed: "
                f"{sorted(NON_CLAIM_CAUSES)}. It is also extraction-side — this layer "
                "runs nothing and may not borrow C4's verdict names."
            )
        if not isinstance(self.text, str):
            raise TypeError(
                f"NonClaim.text must be a string, got {type(self.text).__name__}: "
                f"{self.text!r}"
            )
        if not isinstance(self.location, Location):
            raise TypeError(
                "NonClaim.location must be a Location variant, got "
                f"{type(self.location).__name__}: {self.location!r}"
            )


# --------------------------------------------------------------------------------
# The structural recognisers
# --------------------------------------------------------------------------------

#: How far either side of a span the recognisers below look. Bounded, not because the
#: patterns would match further away, but because an unbounded scan of the text before
#: each number is O(paper) per number and therefore quadratic per paper — the shape
#: that cost `candidates.py` twenty-two seconds on a four-thousand-line paper. Every
#: pattern here needs fewer than ten characters; the windows are generous multiples.
_WINDOW_BEFORE: Final = 32
_WINDOW_AFTER: Final = 16

#: `n = 412`, `N=412`, `(n = 412)`, `*n* = 412`. The lookbehind is what keeps
#: `median = 412` out, and it reaches *before* the search window, so the window size
#: cannot change the answer. Only spaces and tabs, never a newline: `n =` at the end of
#: one line and a number at the start of the next is a coincidence, not a sample size.
#:
#: The emphasis markers are not decoration. Statistical *n* is conventionally
#: italicised, so a Markdown conversion of a real paper writes `*n* = 412` or
#: `_n_ = 412` far more often than a bare `n = 412`. They are markup rather than part
#: of the name, so the captured name stays `n`.
#:
#: **Underscore emphasis is why this pattern is shaped the way it is.** `_` is
#: word-like, so the lookbehind that keeps `median = 412` and `mean_n = 412` out also
#: rejects `_n_ = 412` if the delimiters are simply added to the character class. The
#: structure that separates them is *where the emphasis opens*: in `_n_` the opening
#: `_` is preceded by a non-word character or the start of the text, while in
#: `mean_n_` it is preceded by `mean`. So the lookbehind moved outward, to the front of
#: the whole group, rather than being loosened.
#:
#: `(?(1)\1)` is a conditional backreference: *if* an opening delimiter matched, the
#: closing one must be the same string. That is what makes the emphasis balanced, and
#: it rejects three shapes the "non-word before the opener" rule alone would admit —
#: `_n = 412` and `N_ = 412` (unclosed: an identifier, not emphasis) and `__n_ = 412`
#: (mismatched). Getting this wrong in either direction is costly and not symmetric:
#: a missed N is admitted as a `Claim` and pollutes the coverage denominator with an
#: item nothing can ever re-derive, while a false N removes a real claim from it.
_SAMPLE_SIZE: Final = re.compile(
    r"(?<![A-Za-z0-9_])([*_]{1,2})?([nN])(?(1)\1)[ \t]*=[ \t]*\Z"
)

#: An operator immediately before the number, which makes the number the operator's
#: operand rather than a value in its own right: the magnitude of a bound, the margin
#: of a ±. These are exactly the operators `value.py` parses, so a widened candidate
#: covering the operator lands on the right variant.
_OPERATOR_BEFORE: Final = re.compile(r"(?:<=|>=|[<>≤≥±]|\+/-|\+-)[ \t]*\Z")

#: A number, a dash, then our number: the high endpoint of a range. The digit is
#: load-bearing — without it an em dash used as prose punctuation ("the model — 0.87
#: AUC — beat") would refuse a perfectly good claim. ASCII hyphen is deliberately
#: absent, matching `value.py`: `12-15` is ambiguous against a signed number, and that
#: known recall gap is aspect 1's to keep, not this module's to guess at.
_RANGE_BEFORE: Final = re.compile(r"\d[ \t]*[–—][ \t]*\Z")

#: Our number, then `±` and another number: the centre of a plus-minus.
_MARGIN_AFTER: Final = re.compile(r"[ \t]*(?:±|\+/-|\+-)[ \t]*[+-]?[.\d]")

#: Our number, then a dash and another number: the low endpoint of a range.
_RANGE_AFTER: Final = re.compile(r"[ \t]*[–—][ \t]*[+-]?[.\d]")

#: A digit — or a digit and its decimal point or thousands separator — immediately
#: before the span: the span starts *inside* a longer number. `extract_candidates`
#: never produces this, because a number may not start inside a run of digits, but a
#: proposer handing back a span it computed elsewhere can, and the result grounds
#: perfectly: `"412"[1:3] == "12"`, so the span round-trips while the claim reads
#: `12` out of a paper that says `412`. Of every fragment shape this is the one that
#: passes the obvious check, so it is the one worth catching.
_NUMBER_BEFORE: Final = re.compile(r"\d[.,]?\Z")

#: The same cut at the other end: `0.87` sliced to `0.8`, `412` sliced to `41`.
_NUMBER_AFTER: Final = re.compile(r"[.,]?\d")

#: The characters a span can start with and still be a slice *taken out of* a longer
#: number, which is the only shape `_NUMBER_BEFORE` describes. A span beginning `<`,
#: `≥` or `≈` cannot be one — no number contains those — so a digit in front of it is
#: the end of a neighbouring name (`I²<50`, `ΔR2≈0.38`), not a truncated value.
#:
#: The sign stays in the set deliberately, and it is the case worth stating: a
#: proposer slicing `12-15` at the hyphen yields `-15`, which grounds and reads a
#: negative value out of a paper that wrote a range. Narrowing the guard past the sign
#: would lose that.
_SLICEABLE_START: Final = re.compile(r"[-+.,\d]")


def _sample_size_name(text: str, span: CharSpan) -> str | None:
    """The name the paper gave this sample size (`"n"` / `"N"`), or `None`.

    Purely structural: an `n` or `N`, an `=`, and the number. It reads nothing about
    what the number means, which is the same discipline `candidates.py` applies to its
    section hints. The consequence, stated rather than hidden: an `n = 3` that is a
    hyperparameter in an equation is indistinguishable from a sample size by this
    rule, and comes out a `StudyParameter`. That direction is the safe one — both are
    things no execution re-derives, and neither belongs in the claim denominator.

    The name is recorded **verbatim**, so `N = 412` yields `"N"`. `StudyParameter.name`
    is documented as the parameter *as the paper named it*; a case-folded name would be
    this module's rendering rather than the paper's, and C7 can fold case when it looks
    one up.
    """
    match = _SAMPLE_SIZE.search(
        text, max(0, span.start - _WINDOW_BEFORE), span.start
    )
    # Group 2, not group 1: group 1 is the emphasis delimiter, which is markup.
    return None if match is None else match[2]


def _is_a_fragment(text: str, span: CharSpan) -> bool:
    """Does this span cover only part of a value the paper wrote as a whole?

    Six shapes, all read off characters adjacent to the span: an operator before it, a
    range dash on either side, a ± after it, and a digit on either side — the last two
    being a span that cuts a single number in half.

    The digit-*before* check is the one with a precondition, because it is the one that
    describes a shape rather than a neighbour: it means "this span starts inside a
    longer number", which can only be true of a span that starts like a number. See
    `_SLICEABLE_START` — unconditioned, it refused five real bounds in the fixture
    corpus for the crime of following a name that ends in a digit.

    What it does **not** catch is stated so the guard is not trusted for more than it
    delivers: an interval endpoint written without a marker is a fragment too, and
    recognising one needs the surrounding structure rather than one adjacent character,
    so those still admit as points today. This refuses some fragments and misses
    others; it invents none, and every fragment it refuses is one fewer claim the paper
    never made.
    """
    before = text[max(0, span.start - _WINDOW_BEFORE) : span.start]
    after = text[span.end : span.end + _WINDOW_AFTER]
    starts_like_a_number = (
        _SLICEABLE_START.match(text, span.start, span.start + 1) is not None
    )
    return (
        _OPERATOR_BEFORE.search(before) is not None
        or _RANGE_BEFORE.search(before) is not None
        or (starts_like_a_number and _NUMBER_BEFORE.search(before) is not None)
        or _MARGIN_AFTER.match(after) is not None
        or _RANGE_AFTER.match(after) is not None
        or _NUMBER_AFTER.match(after) is not None
    )


def _is_grounded(text: str, candidate: Candidate) -> bool:
    """Does `candidate.span` address exactly `candidate.text` in this paper?

    Each clause refuses a span that the obvious equality check would let through:

    - `span.end <= len(text)` — Python slicing clamps, so `"abc"[0:1000] == "abc"`
      is `True` and an overrunning span appears to round-trip while recording a
      location that covers a thousand characters of a three-character paper.
    - a non-empty text — `text[5:5] == ""` holds against every paper ever written.
    - a text equal to its own stripped form — `parse_value` strips, so a padded
      candidate would yield a claim whose value is `0.87` and whose location quotes
      ` 0.87`. The near-miss survives review precisely because it looks right.
    """
    return (
        candidate.span.end <= len(text)
        and candidate.text != ""
        and candidate.text == candidate.text.strip()
        and text[candidate.span.start : candidate.span.end] == candidate.text
    )


# --------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------


def admit(
    candidate: Candidate,
    *,
    normalized_text: str,
    metric: str,
    units: str | None = None,
    artifact_hint: str | None = None,
    tolerance_hint: str | None = None,
) -> Claim | NonClaim:
    """Admit `candidate` as a `Claim`, or refuse it with a named cause.

    `normalized_text` is the paper as `normalize_text` returned it — the one form every
    offset in this package is measured against. **It is taken at its word and not
    re-normalized.** `normalize_text` is idempotent, so a defensive call would be
    harmless per claim and O(len(paper)) per claim, which is quadratic over a paper;
    a caller who passes raw text instead gets `ungrounded` refusals rather than wrong
    offsets, which is loud and diagnosable.

    A wrong *type* raises; wrong *data* is recorded. The two must not be confused: a
    `TypeError` recorded as a refusal would put one of our bugs into the discrepancy
    corpus as though it were a fact about the paper, and a refusal raised as an
    exception would lose the rest of the paper to one bad proposal.

    **ORDER IS THE CONTRACT.** The checks run in the sequence below, and the first to
    fire names the cause, because each presupposes the one before it:

    1. `ungrounded` — until the span is known to address this text, nothing else that
       could be said about it means anything.
    2. `partial_value` — the span addresses real text, but the wrong extent of it.
    3. `study_parameter` — the span addresses a whole value, and the value is metadata.
       Ahead of the metric check on purpose: a reported N is not a claim *whatever*
       metric a caller attaches to it, which is what keeps a future proposer from
       confidently labelling `412` as a result.
    4. `unnamed_metric` — the proposal's own coherence, checkable without the paper.
    5. `unparsed_value` — last, because it is the only check that can fail on text the
       paper really does contain in the form it was read.

    Returns a `Claim` or a `NonClaim`. Never `None`, and never a verdict.
    """
    if not isinstance(candidate, Candidate):
        raise TypeError(
            "admit() takes a Candidate; a Claim, a NonClaim or a bare string would "
            f"bypass the grounding this gate exists to perform. Got "
            f"{type(candidate).__name__}: {candidate!r}"
        )
    if not isinstance(normalized_text, str):
        raise TypeError(
            "admit() requires the normalized paper text as a string, got "
            f"{type(normalized_text).__name__}: {normalized_text!r}"
        )
    if not isinstance(metric, str):
        raise TypeError(
            "admit() requires the metric as a string; None is not 'no metric stated' "
            f"but a caller who passed the wrong thing. Got {type(metric).__name__}: "
            f"{metric!r}"
        )
    for name, value in (
        ("units", units),
        ("artifact_hint", artifact_hint),
        ("tolerance_hint", tolerance_hint),
    ):
        if value is not None and not isinstance(value, str):
            raise TypeError(
                f"admit() requires {name} to be a string or None, got "
                f"{type(value).__name__}: {value!r}"
            )

    def refuse(cause: str) -> NonClaim:
        return NonClaim(
            cause=cause, text=candidate.text, location=candidate.span
        )

    if not _is_grounded(normalized_text, candidate):
        return refuse(CAUSE_UNGROUNDED)
    if _is_a_fragment(normalized_text, candidate.span):
        return refuse(CAUSE_PARTIAL_VALUE)
    if _sample_size_name(normalized_text, candidate.span) is not None:
        return refuse(CAUSE_STUDY_PARAMETER)
    if not metric.strip():
        return refuse(CAUSE_UNNAMED_METRIC)

    reported_value = parse_value(candidate.text)
    if reported_value is None:
        return refuse(CAUSE_UNPARSED_VALUE)

    return Claim(
        reported_value=reported_value,
        units=units,
        metric=metric,
        location=candidate.span,
        artifact_hint=artifact_hint,
        tolerance_hint=tolerance_hint,
    )


def study_parameters(raw: str) -> tuple[StudyParameter, ...]:
    """Every reported sample size in `raw`, in deterministic document order (M11).

    The document-level counterpart to `admit`, and the sole constructor of a
    `StudyParameter` from a paper. The two are driven by the same recogniser, so they
    cannot disagree about what a sample size is: what this function emits is exactly
    what `admit` refuses with `study_parameter`, and `tests/extract/
    test_study_population.py` asserts that correspondence over a whole document rather
    than leaving it to the two call sites to stay in step.

    `raw` is normalized on the way in and every offset indexes that normalized text,
    the same contract `extract_candidates` and `hash_paper` follow. Candidates come
    from `extract_candidates`, so the numbers found here are the same numbers found
    everywhere else in the package, tokenized by the same rule.

    **Never a `Claim`.** No execution re-derives a sample size, so admitting N as a
    claim would drop a permanently-unbindable item into the coverage denominator the
    Phase 0 gate reads, and the number would come out lower for a reason that has
    nothing to do with how well Plumb works (`study.py` states this at length).
    """
    text = normalize_text(raw)
    parameters: list[StudyParameter] = []
    for candidate in extract_candidates(text):
        name = _sample_size_name(text, candidate.span)
        if name is None:
            continue
        value = parse_value(candidate.text)
        if value is None:
            # Unreachable while the two number grammars agree, which
            # `test_study_population.py` pins over a numeric corpus rather than
            # trusting. Skipping is right if it ever does happen: this function
            # promises sample sizes, and a number it cannot read is not one.
            continue
        parameters.append(
            StudyParameter(name=name, value=value, location=candidate.span)
        )
    return tuple(
        sorted(
            parameters,
            key=lambda parameter: (
                location_sort_key(parameter.location),
                parameter.name,
            ),
        )
    )
