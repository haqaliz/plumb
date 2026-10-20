"""statcheck: recompute the p a paper reports from its own test statistic and df.

Conservative by construction, because a false "inconsistency" is the one thing this feature must
never produce:

- it only reads an **explicitly reported** statistic — `t(28) = 2.41, p = .03`, `F(1, 28) = …`,
  `χ²(1) = …`, `z = …`, `r(28) = …` — never a number inferred from prose;
- an `r` is converted to its t equivalent; a missing df is `NOT_APPLICABLE`, not a guess;
- `t`, `z` and `r` are compared against **both** the two-sided and the one-sided p, so a
  one-sided report the paper did not label can never be flagged;
- `p < .001` is checked as a bound, not as a point;
- the reported p is compared at its own written precision (half-unit band), so rounding is never
  an inconsistency.

`F` and `χ²` are one-sided by construction and compared as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import math
import re

from plumb.consistency.distribution import p_chi2, p_f, p_t_two_sided, p_z_two_sided
from plumb.extract.location import CharSpan

__all__ = ["Statistic", "scan_statistics"]

_STAT = re.compile(
    r"(?<![\w.])(?P<kind>t|F|χ2|χ²|chi2|X2|z|r)\s*"
    r"(?:\(\s*(?P<df1>\d+)\s*(?:,\s*(?P<df2>\d+)\s*)?\))?\s*=\s*"
    r"(?P<value>[-−]?\d*\.?\d+)\s*,\s*(?:p|P)\s*(?P<op>[=<>])\s*(?P<p>\.?\d*\.?\d+)"
)

#: Kinds whose p is one-sided by construction.
_ONE_SIDED = {"F", "chi2"}


@dataclass(frozen=True)
class Statistic:
    """One reported test statistic, the p it claims, and whether they agree."""

    kind: str  # "t" | "F" | "chi2" | "z" | "r"
    span: CharSpan
    reported: str
    label: str  # INTERNAL_INCONSISTENCY | CONSISTENT | NOT_APPLICABLE
    detail: str


def _decimal(text: str) -> Decimal:
    return Decimal(text.replace("−", "-"))


def _band(p_text: str) -> Decimal:
    """Half a unit in the reported p's last written place, as a Decimal."""
    places = len(p_text.split(".", 1)[1]) if "." in p_text else 0
    return Decimal(5) / (Decimal(10) ** (places + 1))


def _normalized_kind(raw: str) -> str:
    return "chi2" if raw in {"χ2", "χ²", "chi2", "X2"} else raw


def _agrees(reported: Decimal, recomputed: float, p_text: str, op: str) -> bool:
    if op == "<":
        return recomputed < float(reported)
    if op == ">":
        return recomputed > float(reported)
    return abs(Decimal(repr(recomputed)) - reported) <= _band(p_text)


def scan_statistics(text: str) -> list[Statistic]:
    """Every explicitly reported statistic in `text`, with its own label."""
    found: list[Statistic] = []
    for match in _STAT.finditer(text):
        kind = _normalized_kind(match.group("kind"))
        span = CharSpan(match.start(), match.end())
        reported = match.group("p")
        shown = f"{kind}({match.group('df1')}) = {match.group('value')}, p {match.group('op')} {reported}"
        try:
            value = float(match.group("value").replace("−", "-"))
            p_reported = _decimal(reported)
        except (ValueError, InvalidOperation):
            found.append(Statistic(kind, span, shown, "NOT_APPLICABLE", "unreadable value"))
            continue
        df1 = match.group("df1")
        df2 = match.group("df2")
        if kind in {"t", "r"} and df1 is None:
            found.append(Statistic(kind, span, shown, "NOT_APPLICABLE", "no df reported"))
            continue
        if kind == "F" and (df1 is None or df2 is None):
            found.append(Statistic(kind, span, shown, "NOT_APPLICABLE", "no df reported"))
            continue
        if kind in {"chi2"} and df1 is None:
            found.append(Statistic(kind, span, shown, "NOT_APPLICABLE", "no df reported"))
            continue
        if (df1 is not None and int(df1) <= 0) or (df2 is not None and int(df2) <= 0):
            found.append(Statistic(kind, span, shown, "NOT_APPLICABLE", "df must be positive"))
            continue

        if kind == "t":
            two = p_t_two_sided(value, int(df1))
        elif kind == "z":
            two = p_z_two_sided(value)
        elif kind == "r":
            df = int(df1)
            if not -1.0 < value < 1.0:
                found.append(Statistic(kind, span, shown, "NOT_APPLICABLE", "r outside (-1, 1)"))
                continue
            two = p_t_two_sided(value * math.sqrt(df / (1.0 - value * value)), df)
        elif kind == "F":
            two = p_f(value, int(df1), int(df2))
        else:  # chi2
            two = p_chi2(value, int(df1))

        op = match.group("op")
        agrees = _agrees(p_reported, two, reported, op)
        if not agrees and kind not in _ONE_SIDED:
            agrees = _agrees(p_reported, two / 2.0, reported, op)
        detail = f"recomputed p = {two:.4g} ({_sided(kind)}), reported p {op} {reported}"
        if agrees:
            found.append(Statistic(kind, span, shown, "CONSISTENT", detail))
        else:
            found.append(
                Statistic(
                    kind, span, shown, "INTERNAL_INCONSISTENCY",
                    detail + " — the paper's own statistic and p disagree",
                )
            )
    return found


def _sided(kind: str) -> str:
    return "one-sided" if kind in _ONE_SIDED else "two-sided"
