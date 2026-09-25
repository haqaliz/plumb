"""Strict decimals, written precision, tolerance, and the context C4 computes in.

**No float, ever** (risk R2, `docs/ROADMAP.md`). A located value becomes a
`Decimal` only through `strict_decimal`, which reads a plain number — sign,
ASCII digits, optional fraction, optional exponent — and nothing else. A
thousands separator, a `%`, `NaN` or `inf` is refused rather than interpreted:
the located text is the run's own output and is read literally.

**Written precision is the exponent.** A `Decimal` built from text keeps the
digits the text wrote (`Decimal("0.870")` has exponent −3), so
`half_unit(d)` — half a unit in the last written digit — is the band a rounded
number stands for. Built from a string, never from a scaled product:
`Decimal("0.87") * 100` is `87.00`, whose exponent no longer says what was
written.

**One pinned context.** Every comparison runs in `CONTEXT`, not the thread's
ambient `decimal` context, so a caller's precision or rounding setting cannot
change a verdict. `Inexact` is trapped: arithmetic that would round is a harness
bug that raises, never a silently rounded comparison. The limits in
`strict_decimal` (40 significant digits, adjusted exponent within ±40) keep every
real input far inside the context's 100-digit precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
)
import re

__all__ = ["CONTEXT", "Tolerance", "half_unit", "strict_decimal"]

CONTEXT = Context(
    prec=100,
    rounding=ROUND_HALF_EVEN,
    traps=[InvalidOperation, Inexact, Overflow, DivisionByZero],
)

_STRICT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", re.ASCII)
_MAX_DIGITS = 40
_MAX_ADJUSTED = 40


def strict_decimal(text: str) -> Decimal | None:
    """A plain number as a `Decimal`, or `None` — never a guess, never a float."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not _STRICT.fullmatch(stripped):
        return None
    value = Decimal(stripped)
    if len(value.as_tuple().digits) > _MAX_DIGITS or abs(value.adjusted()) > _MAX_ADJUSTED:
        return None
    return value


def half_unit(value: Decimal) -> Decimal:
    """Half a unit in the last digit `value` was written with: `0.87` → `0.005`."""
    return Decimal((0, (5,), value.as_tuple().exponent - 1))


@dataclass(frozen=True, slots=True)
class Tolerance:
    """An explicit tolerance from a binding: absolute, or relative to the reported value."""

    kind: str  # "abs" | "rel"
    value: Decimal

    def __post_init__(self) -> None:
        if self.kind not in ("abs", "rel"):
            raise ValueError(f"tolerance kind must be 'abs' or 'rel', got {self.kind!r}")
        if type(self.value) is not Decimal:
            raise TypeError(
                f"tolerance value must be a Decimal, got {type(self.value).__name__}"
            )
        if not self.value.is_finite() or self.value < 0:
            raise ValueError(f"tolerance must be finite and non-negative, got {self.value}")
