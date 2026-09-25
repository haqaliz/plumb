"""Strict decimals, written precision, and the pinned context C4 computes in.

A located value becomes a `Decimal` only through `strict_decimal`: a number and
nothing else, never via `float`. Anything a paper's typography would add — a
thousands separator, a percent sign — is refused here rather than guessed at,
because the located text is the run's own output and must be read literally.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from plumb.verify.numbers import CONTEXT, Tolerance, half_unit, strict_decimal


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.87", "0.87"),
        ("0.870", "0.870"),
        (" -1.5e3 ", "-1.5E+3"),
        (".5", "0.5"),
        ("12", "12"),
        ("+3.", "3"),
        ("1E-4", "0.0001"),
    ],
)
def test_strict_decimal_accepts_plain_numbers(text: str, expected: str) -> None:
    value = strict_decimal(text)
    assert type(value) is Decimal
    assert value == Decimal(expected)


def test_strict_decimal_keeps_the_written_exponent() -> None:
    assert strict_decimal("0.870").as_tuple().exponent == -3
    assert strict_decimal("0.87").as_tuple().exponent == -2


@pytest.mark.parametrize(
    "text",
    ["1,000", "87%", "NaN", "nan", "inf", "-Infinity", "0x1", "1_0", "", "  ", "1.2.3", "e5",
     "1e", "--1", "١٢"],
)
def test_strict_decimal_refuses_anything_else(text: str) -> None:
    assert strict_decimal(text) is None


def test_strict_decimal_refuses_more_than_forty_significant_digits() -> None:
    assert strict_decimal("1" * 40) is not None
    assert strict_decimal("1" * 41) is None


def test_strict_decimal_refuses_an_extreme_exponent() -> None:
    assert strict_decimal("1e40") is not None
    assert strict_decimal("1e41") is None
    assert strict_decimal("1e-41") is None


def test_strict_decimal_refuses_a_non_string() -> None:
    assert strict_decimal(0.87) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("text", "half"),
    [("0.87", "0.005"), ("0.870", "0.0005"), ("12", "0.5"), ("1.5e3", "50"), ("-2.25", "0.005")],
)
def test_half_unit_is_half_the_last_written_digit(text: str, half: str) -> None:
    assert half_unit(Decimal(text)) == Decimal(half)


def test_the_context_traps_inexact_arithmetic() -> None:
    from decimal import Inexact

    with pytest.raises(Inexact):
        CONTEXT.divide(Decimal(1), Decimal(3))


def test_tolerance_is_a_frozen_record() -> None:
    tolerance = Tolerance(kind="abs", value=Decimal("0.01"))
    with pytest.raises(AttributeError):
        tolerance.value = Decimal(0)  # type: ignore[misc]


def test_tolerance_refuses_an_unknown_kind_a_float_or_a_negative() -> None:
    with pytest.raises(ValueError):
        Tolerance(kind="pct", value=Decimal("1"))
    with pytest.raises(TypeError):
        Tolerance(kind="abs", value=0.01)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Tolerance(kind="rel", value=Decimal("-0.1"))
