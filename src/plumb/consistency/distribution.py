"""p-values without SciPy: the two special functions and the four test families.

Not a statistics library. `t`/`F` use the regularized incomplete beta (continued fraction,
Numerical Recipes' `betacf`); `chi2` uses the upper regularized gamma (`gser`/`gcf`); `z` is
`statistics.NormalDist`. Deterministic, ~1e-12 accurate on the df range papers use, which is far
inside the rounding band of a reported p.
"""

from __future__ import annotations

import math
from statistics import NormalDist

__all__ = ["p_chi2", "p_f", "p_t_one_sided", "p_t_two_sided", "p_z_two_sided"]

_EPS = 3e-14
_FPMIN = 1e-300
_MAXIT = 500


def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, _MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = 1.0 + aa / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """The regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _gser(a: float, x: float) -> float:
    """The lower regularized gamma P(a, x) by series."""
    ap, delta, total = a, 1.0 / a, 1.0 / a
    for _ in range(_MAXIT):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * _EPS:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float) -> float:
    """The upper regularized gamma Q(a, x) by continued fraction."""
    b, c, d = x + 1.0 - a, 1.0 / _FPMIN, 1.0 / (x + 1.0 - a)
    h = d
    for i in range(1, _MAXIT + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < _FPMIN:
            d = _FPMIN
        c = b + an / c
        if abs(c) < _FPMIN:
            c = _FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def _gammaq(a: float, x: float) -> float:
    """The upper regularized gamma Q(a, x)."""
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gser(a, x)
    return _gcf(a, x)


def p_z_two_sided(z: float) -> float:
    """Two-sided normal p."""
    return 2.0 * (1.0 - NormalDist().cdf(abs(z)))


def p_t_two_sided(t: float, df: float) -> float:
    """Two-sided t p."""
    return _betai(df / 2.0, 0.5, df / (df + t * t))


def p_t_one_sided(t: float, df: float) -> float:
    """One-sided t p, in the direction of the reported statistic's sign."""
    return p_t_two_sided(t, df) / 2.0


def p_f(f: float, df1: float, df2: float) -> float:
    """Upper-tail F p."""
    return _betai(df2 / 2.0, df1 / 2.0, df2 / (df2 + df1 * f))


def p_chi2(chi2: float, df: float) -> float:
    """Upper-tail chi-square p."""
    return _gammaq(df / 2.0, chi2 / 2.0)
