"""GRIM: a reported mean must be reachable at its written precision for an integer N.

A mean of integer-valued items over `N` observations is a multiple of `1 / (N · 10^d)` for a mean
reported to `d` decimals. `3.72` with `N = 40` needs `3.72 · 40 = 148.8`, which is not an integer,
so no set of 40 integer responses has that mean.

The gate is deliberately narrow — one explicit `mean = …` and one `N = …` in the same sentence.
GRIM only applies to means of integer-valued items, which prose cannot establish, so a
`CONSISTENT` label is a *necessary* check, never a sufficient one; a finding is the only strong
direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from plumb.extract.location import CharSpan

__all__ = ["GrimFinding", "scan_means"]

_MEAN = re.compile(
    r"\b(?:mean|M)\b\s*(?:was|is|of|=|\()?\s*[=(]?\s*(?P<value>-?\d+\.\d+)"
)
_N = re.compile(r"\b[Nn]\s*=\s*(?P<n>\d+)\b")
#: Sentence boundaries only where punctuation is followed by whitespace — a decimal point in
#: `3.72` is never a boundary.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str):
    """(offset, sentence) pairs without splitting decimals."""
    start = 0
    for match in _SENTENCE.finditer(text):
        yield start, text[start:match.start()]
        start = match.end()
    yield start, text[start:]


@dataclass(frozen=True)
class GrimFinding:
    """One mean + N pair and whether the mean is reachable."""

    span: CharSpan
    reported: str
    label: str  # INTERNAL_INCONSISTENCY | CONSISTENT | NOT_APPLICABLE
    detail: str


def scan_means(text: str) -> list[GrimFinding]:
    """Every `mean = …` with exactly one `N = …` in its sentence."""
    found: list[GrimFinding] = []
    for offset, body in _sentences(text):
        means = list(_MEAN.finditer(body))
        sizes = list(_N.finditer(body))
        if len(means) != 1 or len(sizes) != 1:
            continue
        mean = means[0]
        span = CharSpan(offset + mean.start(), offset + sizes[0].end())
        reported = f"mean {mean.group('value')}, N = {sizes[0].group('n')}"
        try:
            value = Decimal(mean.group("value"))
        except InvalidOperation:
            found.append(GrimFinding(span, reported, "NOT_APPLICABLE", "unreadable mean"))
            continue
        n = int(sizes[0].group("n"))
        if n <= 0:
            found.append(GrimFinding(span, reported, "NOT_APPLICABLE", "N must be positive"))
            continue
        decimals = len(mean.group("value").split(".", 1)[1])
        product = value * n
        nearest = product.to_integral_value()
        tolerance = Decimal(n) * Decimal(5) / (Decimal(10) ** (decimals + 1))
        reachable = abs(product - nearest) <= tolerance
        detail = (
            f"{mean.group('value')} × {n} = {product}; nearest integer {nearest} is "
            f"{abs(product - nearest)} away (tolerance {tolerance})"
        )
        label = "CONSISTENT" if reachable else "INTERNAL_INCONSISTENCY"
        found.append(GrimFinding(span, reported, label, detail))
    return found
