"""The decision: does the re-derived value hold the paper's claim? (M3)

`decide(reported, units, located, located_half_unit, tolerance, scale)` is pure
`Decimal` arithmetic in the pinned `CONTEXT` — no I/O, no run, no model. It is
called only once a single value has been located in a fresh artifact of a run
that succeeded; everything that can go wrong before that is a cause decided
elsewhere.

**The order is the contract** (`docs/planning/binding-verdict/prd.md` D1–D7).

1. *Kind gate (D3).* Only `Point` and `Bound` are compared. `PlusMinus`,
   `Interval`, `Range` and `Approximate` are `UNSUPPORTED_VALUE_KIND`: what their
   margin or endpoints must match is not stated by the notation, and guessing it
   is how a harness manufactures a `DIVERGED`.
2. *Scale gate (D4).* A percent claim must declare the artifact's scale, or it is
   `UNIT_UNDECLARED` — `87%` against a run's `0.87` is a unit question, not a
   contradiction. The re-derived value is `located × scale`; the artifact's own
   half-unit is `located_half_unit × scale`, **never** the product's exponent
   (`0.87 × 100` is `87.00`, which claims a precision the run never wrote).
3. For a `Point`:

   a. *Round integers (D1a).* `10,000` may be exact or rounded to the thousand;
      without a tolerance it is `PRECISION_AMBIGUOUS`.
   b. *Coarse artifact (D7).* If the run wrote fewer digits than the paper and
      the paper's value lies within the run's own rounding, the run cannot decide
      the claim → `ARTIFACT_PRECISION_COARSER`. This comes **first**: a run that
      printed `0.9` against a paper's `0.90` lands inside the paper's band, but its
      true value is anywhere in [0.85, 0.95] — reading that as `REPRODUCED` would
      be a false pass. It also precedes tolerance, deliberately.
   c. *Written precision (D1).* The reported value stands for the closed band
      ± half a unit in its last written digit. Inside it → `REPRODUCED`. Closed,
      because at an exact half-unit the paper's rounding convention is unknown,
      and the boundary errs away from `DIVERGED`.
   d. *Explicit tolerance (D2).* Inside `v ± t` (or `v ± r·|v|`) →
      `WITHIN-TOLERANCE`. A relative tolerance of a reported zero is
      `NO_TOLERANCE`.
   e. Otherwise `DIVERGED`: the paper's own written precision was a defensible
      tolerance, and the run's value falls outside it.

4. For a `Bound`, the same shape: the run's rounding straddles the threshold →
   `ARTIFACT_PRECISION_COARSER` (first, for the same reason: `0.05` printed for
   `p <= 0.05` may have been `0.0504`); the operator holds → `REPRODUCED`; the operator
   holds against a threshold widened by the tolerance → `WITHIN-TOLERANCE`;
   otherwise `DIVERGED`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import operator

from plumb.extract.value import Bound, ClaimValue, Point
from plumb.verify.causes import (
    ARTIFACT_PRECISION_COARSER,
    NO_TOLERANCE,
    PRECISION_AMBIGUOUS,
    UNIT_UNDECLARED,
    UNSUPPORTED_VALUE_KIND,
)
from plumb.verify.numbers import CONTEXT, Tolerance, half_unit

__all__ = [
    "DIVERGED",
    "REPRODUCED",
    "UNVERIFIED",
    "VERDICTS",
    "WITHIN_TOLERANCE",
    "Decision",
    "decide",
]

REPRODUCED = "REPRODUCED"
WITHIN_TOLERANCE = "WITHIN-TOLERANCE"
DIVERGED = "DIVERGED"
UNVERIFIED = "UNVERIFIED"
VERDICTS = frozenset({REPRODUCED, WITHIN_TOLERANCE, DIVERGED, UNVERIFIED})

Band = tuple[Decimal, Decimal]

_OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


@dataclass(frozen=True, slots=True)
class Decision:
    """What was decided, and the numbers that decided it."""

    verdict: str
    cause: str | None
    rederived: Decimal | None  # located × scale; None when a gate stopped it first
    band: Band | None  # a Point's written-precision band
    tolerance_band: Band | None  # a Point's explicit tolerance band, when one was used
    threshold: Decimal | None  # a Bound's threshold as the paper wrote it
    tolerance_threshold: Decimal | None  # a Bound's threshold widened by the tolerance
    delta: Decimal | None  # rederived − reported value (or threshold)


def decide(
    reported: ClaimValue,
    units: str | None,
    located: Decimal,
    located_half_unit: Decimal,
    tolerance: Tolerance | None,
    scale: Decimal | None,
) -> Decision:
    """Decide one claim against one located value."""
    for name, value in (("located", located), ("located_half_unit", located_half_unit)):
        if type(value) is not Decimal:
            raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if scale is not None and type(scale) is not Decimal:
        raise TypeError(f"scale must be a Decimal, got {type(scale).__name__}")
    if tolerance is not None and not isinstance(tolerance, Tolerance):
        raise TypeError(f"tolerance must be a Tolerance, got {type(tolerance).__name__}")

    if not isinstance(reported, (Point, Bound)):
        return _unverified(UNSUPPORTED_VALUE_KIND)
    if scale is None and (units == "%" or "%" in reported.text):
        return _unverified(UNIT_UNDECLARED)

    factor = Decimal(1) if scale is None else scale
    rederived = CONTEXT.multiply(located, factor)
    artifact_half = CONTEXT.multiply(located_half_unit, factor)
    if isinstance(reported, Point):
        return _point(reported.value, rederived, artifact_half, tolerance)
    return _bound(reported, rederived, artifact_half, tolerance)


def _point(v: Decimal, re: Decimal, a: Decimal, tolerance: Tolerance | None) -> Decision:
    delta = CONTEXT.subtract(re, v)

    def result(verdict: str, cause: str | None = None, band=None, tolerance_band=None):
        return Decision(verdict, cause, re, band, tolerance_band, None, None, delta)

    if tolerance is None and _round_integer(v):
        return result(UNVERIFIED, PRECISION_AMBIGUOUS)

    h = half_unit(v)
    band = _around(v, h)
    if a > h and _inside(v, _around(re, a)):
        return result(UNVERIFIED, ARTIFACT_PRECISION_COARSER, band=band)
    if _inside(re, band):
        return result(REPRODUCED, band=band)
    if tolerance is not None:
        width = _width(tolerance, v)
        if width is None:
            return result(UNVERIFIED, NO_TOLERANCE, band=band)
        tolerance_band = _around(v, width)
        if _inside(re, tolerance_band):
            return result(WITHIN_TOLERANCE, band=band, tolerance_band=tolerance_band)
        return result(DIVERGED, band=band, tolerance_band=tolerance_band)
    return result(DIVERGED, band=band)


def _bound(reported: Bound, re: Decimal, a: Decimal, tolerance: Tolerance | None) -> Decision:
    m = reported.magnitude
    holds = _OPS[reported.op]
    delta = CONTEXT.subtract(re, m)

    def result(verdict: str, cause: str | None = None, widened: Decimal | None = None):
        return Decision(verdict, cause, re, None, None, m, widened, delta)

    low, high = CONTEXT.subtract(re, a), CONTEXT.add(re, a)
    if holds(low, m) != holds(high, m):
        return result(UNVERIFIED, ARTIFACT_PRECISION_COARSER)
    if holds(re, m):
        return result(REPRODUCED)
    if tolerance is not None:
        width = _width(tolerance, m)
        if width is None:
            return result(UNVERIFIED, NO_TOLERANCE)
        widened = CONTEXT.add(m, width) if reported.op in ("<", "<=") else CONTEXT.subtract(m, width)
        if holds(re, widened):
            return result(WITHIN_TOLERANCE, widened=widened)
        return result(DIVERGED, widened=widened)
    return result(DIVERGED)


def _unverified(cause: str) -> Decision:
    return Decision(UNVERIFIED, cause, None, None, None, None, None, None)


def _round_integer(v: Decimal) -> bool:
    """An integer written without decimals whose last digit is zero: `10,000`, `20`."""
    return v.as_tuple().exponent == 0 and v != 0 and v.normalize().as_tuple().exponent > 0


def _width(tolerance: Tolerance, reference: Decimal) -> Decimal | None:
    if tolerance.kind == "abs":
        return tolerance.value
    if reference == 0:
        return None
    return CONTEXT.multiply(tolerance.value, reference.copy_abs())


def _around(center: Decimal, width: Decimal) -> Band:
    return CONTEXT.subtract(center, width), CONTEXT.add(center, width)


def _inside(value: Decimal, band: Band) -> bool:
    return band[0] <= value <= band[1]
