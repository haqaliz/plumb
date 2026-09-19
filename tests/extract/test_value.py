"""Tests for the `ClaimValue` tagged union (M2, plan Phase 2).

These tests are the guardrail for risk **R2** (`docs/ROADMAP.md:57`): a float
anywhere in the value path is the upstream seed of a false `DIVERGED` verdict. They
are load-bearing, not stylistic — a change that makes any of them pass "more
conveniently" (by normalizing significant figures, by collapsing a bound to its
magnitude, by reaching for `float`) has broken the product, not the test.
"""

import ast
import inspect
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from plumb.extract.value import (
    Approximate,
    Bound,
    ClaimValue,
    Interval,
    Point,
    PlusMinus,
    Range,
    parse_value,
)

# The six fixtures of design decision D1 (plan §0). Each is a *kind* of value, not a
# spelling of one. `EN_DASH` is spelled out because an editor or a copy-paste through
# a lossy tool will silently turn U+2013 into a hyphen, which would make the Range
# fixture test something else entirely.
EN_DASH = "–"
RANGE_FIXTURE = f"12{EN_DASH}15%"

D1_FIXTURES = [
    ("0.87", Point),
    ("p < 0.001", Bound),
    ("0.85 ± 0.03", PlusMinus),
    ("95% CI [0.81, 0.89]", Interval),
    (RANGE_FIXTURE, Range),
    ("~10,000", Approximate),
]


def test_range_fixture_really_uses_an_en_dash() -> None:
    """Guard the guard: U+2013 is not a hyphen and must not be "fixed" into one."""
    assert EN_DASH in RANGE_FIXTURE
    assert "-" not in RANGE_FIXTURE
    assert ord(EN_DASH) == 0x2013


@pytest.mark.parametrize(("text", "variant"), D1_FIXTURES)
def test_parse_value_returns_the_d1_variant(text: str, variant: type) -> None:
    value = parse_value(text)
    assert type(value) is variant


@pytest.mark.parametrize(("text", "variant"), D1_FIXTURES)
def test_text_round_trips_verbatim(text: str, variant: type) -> None:
    """`text` is the paper's own spelling, byte for byte."""
    value = parse_value(text)
    assert value is not None
    assert value.text == text


@pytest.mark.parametrize(("text", "variant"), D1_FIXTURES)
def test_every_variant_is_a_claim_value(text: str, variant: type) -> None:
    value = parse_value(text)
    assert isinstance(value, ClaimValue)


# --------------------------------------------------------------------------------
# Per-variant components
# --------------------------------------------------------------------------------


def test_point_carries_a_decimal() -> None:
    value = parse_value("0.87")
    assert value == Point(text="0.87", value=Decimal("0.87"))


def test_bound_keeps_its_operator_and_is_never_collapsed() -> None:
    """`p < 0.001` is NOT the value 0.001 (plan §6). Collapsing it would let a
    re-derived 0.0009 read as a mismatch against a number the paper never claimed."""
    value = parse_value("p < 0.001")
    assert isinstance(value, Bound)
    assert value.op == "<"
    assert value.magnitude == Decimal("0.001")
    # The structural point: a bound and a point are different types, so no caller can
    # accidentally compare one to the other.
    assert not isinstance(value, Point)
    assert type(parse_value("0.001")) is Point


@pytest.mark.parametrize(
    ("text", "expected_op"),
    [
        ("p < 0.001", "<"),
        ("p > 0.05", ">"),
        ("p <= 0.001", "<="),
        ("p >= 0.05", ">="),
        ("p ≤ 0.001", "<="),  # U+2264 LESS-THAN OR EQUAL TO
        ("p ≥ 0.05", ">="),  # U+2265 GREATER-THAN OR EQUAL TO
        ("< 0.001", "<"),
    ],
    ids=["lt", "gt", "le-ascii", "ge-ascii", "le-unicode", "ge-unicode", "bare"],
)
def test_bound_operators(text: str, expected_op: str) -> None:
    value = parse_value(text)
    assert isinstance(value, Bound)
    assert value.op == expected_op
    # Whatever the operator spelling, the paper's own text survives untouched.
    assert value.text == text


def test_plus_minus_splits_center_from_margin() -> None:
    value = parse_value("0.85 ± 0.03")
    assert value == PlusMinus(
        text="0.85 ± 0.03", center=Decimal("0.85"), margin=Decimal("0.03")
    )


def test_plus_minus_accepts_the_ascii_spelling() -> None:
    value = parse_value("0.85 +/- 0.03")
    assert isinstance(value, PlusMinus)
    assert value.center == Decimal("0.85")
    assert value.margin == Decimal("0.03")
    assert value.text == "0.85 +/- 0.03"


def test_interval_treats_the_leading_percent_as_a_confidence_level() -> None:
    """In `95% CI [0.81, 0.89]` the 95 is the confidence LEVEL, not the value
    (plan §6). It must not leak into `low`, `high`, or a Point."""
    value = parse_value("95% CI [0.81, 0.89]")
    assert value == Interval(
        text="95% CI [0.81, 0.89]", low=Decimal("0.81"), high=Decimal("0.89")
    )
    assert Decimal("95") not in (value.low, value.high)


def test_interval_without_a_confidence_prefix() -> None:
    value = parse_value("[0.81, 0.89]")
    assert isinstance(value, Interval)
    assert (value.low, value.high) == (Decimal("0.81"), Decimal("0.89"))


def test_range_uses_the_en_dash_not_a_hyphen() -> None:
    value = parse_value(RANGE_FIXTURE)
    assert value == Range(text=RANGE_FIXTURE, low=Decimal("12"), high=Decimal("15"))


def test_approximate_strips_the_comma_for_the_decimal_only() -> None:
    """The separator is a typographic convention, so it cannot reach the `Decimal`;
    it is part of the paper's text, so it cannot be erased from `text` (plan §6)."""
    value = parse_value("~10,000")
    assert value == Approximate(text="~10,000", value=Decimal("10000"))
    assert value.text == "~10,000"
    assert "," in value.text


def test_approximate_accepts_the_unicode_tilde() -> None:
    value = parse_value("≈ 0.87")  # U+2248 ALMOST EQUAL TO
    assert isinstance(value, Approximate)
    assert value.value == Decimal("0.87")


# --------------------------------------------------------------------------------
# Precision: the reason this phase exists
# --------------------------------------------------------------------------------


def test_decimal_equality_is_numeric_not_representational() -> None:
    """Pinned here so nobody re-derives it the hard way, and so the day CPython's
    `Decimal` changes we hear about it from a test rather than from a wrong verdict.

    `Decimal.__eq__` compares numeric value, not representation: `Decimal("0.870")`
    and `Decimal("0.87")` are equal and hash equal. Significant figures survive in
    `as_tuple()` and `str()` instead. Two consequences the plan (§2 Phase 2) draws
    from this: assert precision on the representation, and let **`text` carry value
    identity** — dedup resting on `Decimal` equality would silently merge `0.87` and
    `0.870`, which must stay two claims.
    """
    assert Decimal("0.870") == Decimal("0.87")
    assert hash(Decimal("0.870")) == hash(Decimal("0.87"))
    assert Decimal("0.870").as_tuple() != Decimal("0.87").as_tuple()


def test_significant_figures_survive() -> None:
    """`0.870` and `0.87` are different reported values and must never be normalized
    together (plan §6). `0.870` states precision to three decimals — the very thing a
    later tolerance band may be derived from — so losing the trailing zero would
    widen or narrow that band against a precision the paper never reported."""
    three_sig_figs = parse_value("0.870")
    two_sig_figs = parse_value("0.87")
    assert isinstance(three_sig_figs, Point)
    assert isinstance(two_sig_figs, Point)

    # The reported digits and scale are carried, exactly.
    assert three_sig_figs.value.as_tuple() == (0, (8, 7, 0), -3)
    assert str(three_sig_figs.value) == "0.870"
    assert three_sig_figs.text == "0.870"

    # ...and are distinguishable from the two-figure reading, which numeric equality
    # alone would not tell you. The two carriers of that distinction:
    assert three_sig_figs.text != two_sig_figs.text
    assert three_sig_figs.value.as_tuple() != two_sig_figs.value.as_tuple()
    assert three_sig_figs != two_sig_figs

    # The specific regression this locks out: a parser that "tidies" its output.
    # `.normalize()` is the tidy-up, and it is exactly what must not happen.
    assert three_sig_figs.value.as_tuple() != (
        three_sig_figs.value.normalize().as_tuple()
    )


def test_value_identity_is_the_verbatim_text_not_the_decimal() -> None:
    """The basis a later aspect must dedup on, pinned here at its boundary case.

    `0.87` and `0.870` are two distinct reported claims. Their `Decimal`s compare
    equal and hash equal, so an identity resting on the `Decimal` would silently
    merge them — losing a claim, and with it the precision a tolerance band is read
    from. Identity rests on the verbatim `text`, which differs. This test fails the
    moment that stops being true.
    """
    coarse = Point(text="0.87", value=Decimal("0.87"))
    fine = Point(text="0.870", value=Decimal("0.870"))

    # The trap: on the Decimals alone these are indistinguishable.
    assert coarse.value == fine.value
    assert hash(coarse.value) == hash(fine.value)

    # The escape: text differs, so the records differ.
    assert coarse.text != fine.text
    assert coarse != fine

    # And identity is text-driven, not Decimal-driven — same text, same record.
    assert coarse == Point(text="0.87", value=Decimal("0.87"))


@pytest.mark.parametrize(
    ("text", "expected_digits", "expected_exponent"),
    [
        ("0.870", (8, 7, 0), -3),
        ("10.0", (1, 0, 0), -1),
        ("1.2300", (1, 2, 3, 0, 0), -4),
        ("0.001", (1,), -3),
        ("12", (1, 2), 0),
        ("~10,000", (1, 0, 0, 0, 0), 0),
    ],
)
def test_the_parser_never_normalizes_away_reported_digits(
    text: str, expected_digits: tuple[int, ...], expected_exponent: int
) -> None:
    """Whatever scale the paper wrote at is the scale we keep — digit for digit."""
    value = parse_value(text)
    assert value is not None
    (component,) = _decimal_components(value)
    assert isinstance(component, Decimal)
    assert component.as_tuple() == (0, expected_digits, expected_exponent)
    # And it round-trips through text, which is how aspect 3 will serialise it.
    assert Decimal(str(component)).as_tuple() == component.as_tuple()


def _decimal_components(value: ClaimValue) -> list[object]:
    return [
        getattr(value, field)
        for field in ("value", "magnitude", "center", "margin", "low", "high")
        if hasattr(value, field)
    ]


@pytest.mark.parametrize(("text", "variant"), D1_FIXTURES)
def test_no_component_is_ever_a_float(text: str, variant: type) -> None:
    """R2: a float in the value path is the upstream seed of a false DIVERGED."""
    value = parse_value(text)
    components = _decimal_components(value)
    assert components, f"{variant.__name__} exposes no numeric component"
    for component in components:
        assert isinstance(component, Decimal)
        assert not isinstance(component, float)


def test_value_module_never_calls_float() -> None:
    """A structural lock on R2: `float(...)` must not appear in the value path at
    all, so no future edit can introduce one without deleting this test."""
    import plumb.extract.value as value_module

    source = Path(inspect.getfile(value_module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    float_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "float"
    ]
    assert float_calls == [], "value.py must never construct a float (R2)"


# --------------------------------------------------------------------------------
# Precedence: `re` is leftmost-first, so alternation ORDER picks the variant
# --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "winner", "loser"),
    [
        (RANGE_FIXTURE, Range, Point),
        ("95% CI [0.81, 0.89]", Interval, Point),
        ("95% CI [0.81, 0.89]", Interval, Range),
        ("~10,000", Approximate, Point),
        ("p < 0.001", Bound, Point),
        ("0.85 ± 0.03", PlusMinus, Point),
        ("0.85 ± 0.03", PlusMinus, Range),
    ],
    ids=[
        "range-beats-point",
        "interval-beats-point",
        "interval-beats-range",
        "approximate-beats-point",
        "bound-beats-point",
        "plusminus-beats-point",
        "plusminus-beats-range",
    ],
)
def test_more_specific_variant_wins(text: str, winner: type, loser: type) -> None:
    """e.g. `12–15%` must not match Point on the leading `12`."""
    value = parse_value(text)
    assert type(value) is winner
    assert type(value) is not loser


def test_exactly_one_pattern_matches_each_fixture() -> None:
    """The plan warns that `re` is leftmost-first, so alternation order decides which
    variant wins. `parse_value` sidesteps that by anchoring every pattern with
    `fullmatch`, which means today **no two patterns overlap** and the order of
    `_PATTERNS` is not load-bearing.

    That is a property worth holding on purpose rather than by luck. This test reads
    the private pattern table deliberately: the day someone adds a looser pattern
    (an ASCII-hyphen range, say) two patterns will match one fixture, this test will
    fail, and they will be forced to think about precedence instead of discovering it
    later as a mis-parsed claim.
    """
    from plumb.extract.value import _PATTERNS

    for text, variant in D1_FIXTURES:
        matching = [
            pattern.pattern for pattern, _ in _PATTERNS if pattern.fullmatch(text)
        ]
        assert len(matching) == 1, (
            f"{text!r} is matched by {len(matching)} patterns, so the order of "
            f"_PATTERNS now decides the variant: {matching}"
        )


# --------------------------------------------------------------------------------
# The caller-decides contract: None, never a guess, never an exception
# --------------------------------------------------------------------------------


UNPARSEABLE = [
    ("", "empty"),
    ("   ", "whitespace-only"),
    ("\n\t", "whitespace-control"),
    ("no numbers here", "prose"),
    ("n/a", "not-applicable"),
    ("[low, high]", "symbolic-interval"),
    ("0.87.", "trailing-punctuation"),
    ("0.87 and 0.99", "two-values-one-string"),
    ("0.87 kg", "unhandled-unit"),
]


@pytest.mark.parametrize(
    "text", [text for text, _ in UNPARSEABLE], ids=[i for _, i in UNPARSEABLE]
)
def test_unparseable_text_returns_none(text: str) -> None:
    """aspect 1 never invents a value; the caller decides what a miss means
    (plan §6, §8.4)."""
    assert parse_value(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "((((",
        "0.87 ± ",
        "[0.81,]",
        "~",
        "p <",
        f"{EN_DASH}15%",
        "\u0000",
        "x" * 10_000,
    ],
)
def test_parse_value_never_raises(text: str) -> None:
    parse_value(text)  # must not raise; a return value of None is fine


def test_parse_value_rejects_a_float_input_instead_of_converting_it() -> None:
    """Fittingly: the one input a value parser must never accept is a float."""
    assert parse_value(0.87) is None  # type: ignore[arg-type]
    assert parse_value(None) is None  # type: ignore[arg-type]


def test_surrounding_whitespace_is_stripped_but_internal_spacing_is_kept() -> None:
    value = parse_value("  0.85 ± 0.03  ")
    assert isinstance(value, PlusMinus)
    assert value.text == "0.85 ± 0.03"


# --------------------------------------------------------------------------------
# Union shape
# --------------------------------------------------------------------------------


def test_claim_value_base_is_not_instantiable() -> None:
    """A bare `ClaimValue` would be a value with no `Decimal` behind it — exactly the
    precision-free object this union exists to prevent."""
    with pytest.raises(TypeError, match="union base"):
        ClaimValue(text="0.87")  # type: ignore[abstract]


@pytest.mark.parametrize(("text", "variant"), D1_FIXTURES)
def test_variants_are_frozen(text: str, variant: type) -> None:
    """A reported value is a fact about a paper; nothing downstream may edit it."""
    value = parse_value(text)
    with pytest.raises(FrozenInstanceError):
        value.text = "tampered"  # type: ignore[misc]
