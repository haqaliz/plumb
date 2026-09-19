"""`ClaimValue`: what a paper actually reported, without losing anything on the way in.

A paper does not report one kind of number. `0.87`, `p < 0.001`, `0.85 ± 0.03`,
`95% CI [0.81, 0.89]`, `12–15%` and `~10,000` are six *kinds* of value, not six
spellings of one, so `ClaimValue` is a tagged union with one variant per kind
(design decision D1 of the aspect plan). Flattening them into a scalar would throw
away exactly the information a later comparison needs: a bound collapsed to its
magnitude turns `p < 0.001` into the claim `p = 0.001`, which the paper never made.

Two rules hold across every variant, and they are the reason this module exists:

1. **`text` is verbatim.** Whatever the paper wrote is kept character for character
   (surrounding whitespace aside). It is the only thing a human can check our
   parse against.
2. **Numeric components are `Decimal`, built from strings.** Never `float(...)`,
   never `Decimal(some_float)`. `Decimal("0.870") != Decimal("0.87")`, so the
   reported significant figures survive; `float("0.1") + float("0.2") != 0.3`, so a
   float that enters here would re-emerge downstream as a tolerance-width
   discrepancy that the paper never contained. That is risk **R2** in
   `docs/ROADMAP.md:57` — a false `DIVERGED` seeded upstream, in the parser, long
   before anything is compared.

`parse_value` reads a value out of a string and returns `None` when it cannot. It
never raises and never invents a value: the *caller* decides what a miss means
(recording a non-claim with a named cause is aspect 2's job). This module emits no
verdicts of any kind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

__all__ = [
    "Approximate",
    "Bound",
    "ClaimValue",
    "Interval",
    "Point",
    "PlusMinus",
    "Range",
    "parse_value",
]


# --------------------------------------------------------------------------------
# The union
# --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClaimValue:
    """Base of the value union. Carries the paper's own text, and nothing else.

    Not instantiable on its own: a bare `ClaimValue` would be a reported value with
    no `Decimal` behind it, which is precisely the precision-free object this union
    exists to prevent.
    """

    text: str

    def __post_init__(self) -> None:
        if type(self) is ClaimValue:
            raise TypeError(
                "ClaimValue is a union base; construct one of its variants "
                "(Point, Bound, PlusMinus, Interval, Range, Approximate)."
            )


@dataclass(frozen=True, slots=True)
class Point(ClaimValue):
    """A single reported number: `0.87`."""

    value: Decimal


@dataclass(frozen=True, slots=True)
class Bound(ClaimValue):
    """A one-sided bound: `p < 0.001`.

    `magnitude` is the threshold, not the value. The paper claims the quantity lies
    on one side of it and says nothing more; collapsing this to `Point(0.001)` would
    invent a claim and make a re-derived `0.0009` look like a contradiction.

    `op` is canonicalised to one of `<`, `<=`, `>`, `>=` so downstream comparison has
    a single spelling to handle; `≤` and `≥` survive verbatim in `text`.
    """

    op: str
    magnitude: Decimal


@dataclass(frozen=True, slots=True)
class PlusMinus(ClaimValue):
    """A centre and a margin: `0.85 ± 0.03`.

    Deliberately not pre-expanded into an `Interval`: the paper reported a centre,
    and what the margin means (SD, SEM, half-width of a CI) is not stated by the
    notation. Turning it into `[0.82, 0.88]` would be our interpretation, not the
    paper's claim.
    """

    center: Decimal
    margin: Decimal


@dataclass(frozen=True, slots=True)
class Interval(ClaimValue):
    """An explicit interval: `95% CI [0.81, 0.89]`.

    Only the endpoints are components. In `95% CI [...]` the leading `95` is the
    *confidence level* — a property of the estimator, not a reported value — so it
    must never surface as an endpoint or as a `Point`. It is preserved in `text`.
    """

    low: Decimal
    high: Decimal


@dataclass(frozen=True, slots=True)
class Range(ClaimValue):
    """A span between two reported numbers: `12–15%`.

    The separator is an en dash (U+2013) or em dash (U+2014), not a hyphen. An ASCII
    hyphen is deliberately not accepted here: `12-15` is ambiguous against a signed
    number, and guessing is how a parser invents claims.
    """

    low: Decimal
    high: Decimal


@dataclass(frozen=True, slots=True)
class Approximate(ClaimValue):
    """A hedged number: `~10,000`.

    A distinct variant because the hedge is part of the claim. Thousands separators
    are stripped from the `Decimal` (they are typography, not magnitude) but stay in
    `text`.
    """

    value: Decimal


# --------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------

# A number as papers write one: optional sign, optional thousands separators,
# optional fraction, optional exponent. Every group is non-capturing so the variant
# patterns below can rely on their own group numbering.
_NUMBER = r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?"

# A trailing unit, tolerated so `12–15%` parses. Only `%` — general unit handling
# belongs to `Claim.units`, not to the value parser, and accepting arbitrary trailing
# tokens here would turn `0.87 kg` into a value with a silently dropped unit.
_PERCENT = r"(?:\s*%)?"

_DASH = "–—"  # EN DASH, EM DASH
_TILDE = "~∼≈≃"  # ~, ∼, ≈, ≃

_OPERATORS = {
    "<": "<",
    ">": ">",
    "<=": "<=",
    ">=": ">=",
    "≤": "<=",  # ≤
    "≥": ">=",  # ≥
}


def _to_decimal(raw: str) -> Decimal | None:
    """String → `Decimal`, thousands separators removed. No float, ever."""
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


def _interval(text: str, match: re.Match[str]) -> ClaimValue | None:
    low, high = _to_decimal(match[1]), _to_decimal(match[2])
    if low is None or high is None:
        return None
    return Interval(text=text, low=low, high=high)


def _plus_minus(text: str, match: re.Match[str]) -> ClaimValue | None:
    center, margin = _to_decimal(match[1]), _to_decimal(match[2])
    if center is None or margin is None:
        return None
    return PlusMinus(text=text, center=center, margin=margin)


def _bound(text: str, match: re.Match[str]) -> ClaimValue | None:
    magnitude = _to_decimal(match[2])
    if magnitude is None:
        return None
    return Bound(text=text, op=_OPERATORS[match[1]], magnitude=magnitude)


def _range(text: str, match: re.Match[str]) -> ClaimValue | None:
    low, high = _to_decimal(match[1]), _to_decimal(match[2])
    if low is None or high is None:
        return None
    return Range(text=text, low=low, high=high)


def _approximate(text: str, match: re.Match[str]) -> ClaimValue | None:
    value = _to_decimal(match[1])
    if value is None:
        return None
    return Approximate(text=text, value=value)


def _point(text: str, match: re.Match[str]) -> ClaimValue | None:
    value = _to_decimal(match[1])
    if value is None:
        return None
    return Point(text=text, value=value)


# ORDER IS THE CONTRACT. The patterns are tried in sequence, most specific first, so
# that `12–15%` is a Range and not a Point that stopped reading after `12`. Every
# pattern is applied with `fullmatch`, which is the second half of the same
# guarantee: a value is the whole string or it is nothing, so trailing text can never
# be silently discarded. Moving an entry up or down this list changes which variant
# wins — `tests/extract/test_value.py` has a case per precedence pair.
_PATTERNS: tuple[tuple[re.Pattern[str], object], ...] = (
    # `95% CI [0.81, 0.89]`, `CI [0.81, 0.89]`, `[0.81, 0.89]`, `(0.81, 0.89)`
    (
        re.compile(
            rf"(?:{_NUMBER}\s*%\s*)?(?:CI\s*)?"
            rf"[\[(]\s*({_NUMBER})\s*,\s*({_NUMBER})\s*[\])]",
            re.IGNORECASE,
        ),
        _interval,
    ),
    # `0.85 ± 0.03`, `0.85 +/- 0.03`
    (
        re.compile(rf"({_NUMBER})\s*(?:±|\+/-|\+-)\s*({_NUMBER}){_PERCENT}"),
        _plus_minus,
    ),
    # `p < 0.001`, `< 0.001`, `FDR ≤ 0.05`
    (
        re.compile(
            rf"(?:[A-Za-z][A-Za-z0-9_.-]*\s*)?"
            rf"(<=|>=|≤|≥|<|>)\s*({_NUMBER}){_PERCENT}"
        ),
        _bound,
    ),
    # `12–15%`
    (re.compile(rf"({_NUMBER})\s*[{_DASH}]\s*({_NUMBER}){_PERCENT}"), _range),
    # `~10,000`, `≈ 0.87`
    (re.compile(rf"[{_TILDE}]\s*({_NUMBER}){_PERCENT}"), _approximate),
    # `0.87`, `15%`
    (re.compile(rf"({_NUMBER}){_PERCENT}"), _point),
)


def parse_value(text: str) -> ClaimValue | None:
    """Read a `ClaimValue` out of `text`, or return `None`.

    `None` means "this parser could not decide", not "there is no value here" and
    certainly not "the value is zero". Aspect 1 never invents a value: the caller
    decides what a miss means. This function does not raise — an unparseable,
    empty, or non-string input is a `None`, because a parser that throws partway
    through a paper is a parser that loses the rest of the paper.
    """
    if not isinstance(text, str):
        return None

    stripped = text.strip()
    if not stripped:
        return None

    for pattern, build in _PATTERNS:
        match = pattern.fullmatch(stripped)
        if match is not None:
            return build(stripped, match)  # type: ignore[operator]
    return None
