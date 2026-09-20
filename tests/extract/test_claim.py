"""Tests for the `Claim` record.

Two contracts here are load-bearing and neither is a style preference:

1. **The `id` excludes `location`** (design decision D2). Aspect 3 merges duplicate
   locations into a single claim and requires the id to be *unchanged* by that merge.
   An id derived from location would make dedup change identity, which is circular.
2. **There is no `confidence` field**, and the test that asserts its absence is a
   guardrail (`CLAUDE.md` #1). See `TestNoConfidence` for why.

The id is derived from `reported_value.text` — the verbatim string — never from the
`Decimal`, because `Decimal("0.870") == Decimal("0.87")` is `True` and an id built on
`Decimal` equality would merge two values the paper reported differently.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan
from plumb.extract.value import ClaimValue, parse_value

# A paragraph the spans below index into, so the fixtures stay plausible rather than
# arbitrary integers.
PARAGRAPH = "The model reached AUC 0.87 on the held-out cohort (n = 412)."


def value(text: str) -> ClaimValue:
    """`parse_value` that fails the test rather than returning `None` into a fixture."""
    parsed = parse_value(text)
    assert parsed is not None, f"fixture text did not parse: {text!r}"
    return parsed


def span_of(needle: str) -> CharSpan:
    """The span a correct extractor would emit for `needle` inside `PARAGRAPH`."""
    start = PARAGRAPH.index(needle)
    return CharSpan(start, start + len(needle))


def claim(**overrides: object) -> Claim:
    """A fully-specified `Claim`, with named fields replaced per test."""
    fields: dict[str, object] = {
        "reported_value": value("0.87"),
        "units": None,
        "metric": "AUC",
        "location": span_of("0.87"),
        "artifact_hint": "notebooks/eval.ipynb",
        "tolerance_hint": None,
    }
    fields.update(overrides)
    return Claim(**fields)  # type: ignore[arg-type]


class TestConstruction:
    @pytest.mark.parametrize(
        "missing",
        [
            "reported_value",
            "units",
            "metric",
            "location",
            "artifact_hint",
            "tolerance_hint",
        ],
    )
    def test_every_field_must_be_stated(self, missing: str) -> None:
        """No field has a default, including the nullable ones.

        `units=None` must be something the caller *said*, not something they got by
        omission: "this metric is dimensionless" and "nobody looked for a unit" are
        different facts, and a default would render them identically.
        """
        fields = {
            "reported_value": value("0.87"),
            "units": None,
            "metric": "AUC",
            "location": span_of("0.87"),
            "artifact_hint": None,
            "tolerance_hint": None,
        }
        del fields[missing]

        with pytest.raises(TypeError):
            Claim(**fields)  # type: ignore[arg-type]

    def test_fields_round_trip_verbatim(self) -> None:
        loc = span_of("0.87")
        reported = value("0.87")
        c = Claim(
            reported_value=reported,
            units="%",
            metric="AUC",
            location=loc,
            artifact_hint="notebooks/eval.ipynb",
            tolerance_hint="±0.01",
        )

        assert c.reported_value is reported
        assert c.units == "%"
        assert c.metric == "AUC"
        assert c.location is loc
        assert c.artifact_hint == "notebooks/eval.ipynb"
        assert c.tolerance_hint == "±0.01"

    @pytest.mark.parametrize("empty", ["", " ", "\t", "\n  "])
    def test_metric_must_not_be_empty_or_whitespace(self, empty: str) -> None:
        """A claim without a named metric cannot be aimed at anything.

        C4 binds a claim by pointing a locator at a *named* quantity. With no metric,
        a downstream capability would have to re-interpret the surrounding prose to
        work out what the number was — which is the guessing this project does not do.
        """
        with pytest.raises(ValueError):
            claim(metric=empty)

    def test_metric_must_be_a_string(self) -> None:
        with pytest.raises(TypeError):
            claim(metric=None)

    def test_units_may_be_none_for_a_dimensionless_metric(self) -> None:
        """An AUC has no unit. `None` is the honest answer, not an error."""
        c = claim(metric="AUC", units=None)

        assert c.units is None

    def test_units_may_be_a_string(self) -> None:
        assert claim(metric="sensitivity", units="%").units == "%"

    def test_artifact_hint_may_be_none(self) -> None:
        assert claim(artifact_hint=None).artifact_hint is None

    def test_tolerance_hint_may_be_none(self) -> None:
        assert claim(tolerance_hint=None).tolerance_hint is None

    def test_tolerance_hint_is_carried_verbatim_and_never_interpreted(self) -> None:
        """The slot exists; the policy does not, and must not be invented here.

        What a stated tolerance *means* (absolute, relative, inherited from the
        metric) is an open design question owned elsewhere. This record carries the
        paper's words unparsed so that the decision stays open; a parsed numeric
        tolerance sitting on the record would quietly settle it.
        """
        c = claim(tolerance_hint="within 1 percentage point")

        assert c.tolerance_hint == "within 1 percentage point"
        assert not hasattr(c, "tolerance")

    def test_reported_value_must_be_a_claim_value(self) -> None:
        """A bare string would duck-type far enough to poison the id and no further."""
        with pytest.raises(TypeError):
            claim(reported_value="0.87")

    def test_location_must_be_a_location(self) -> None:
        with pytest.raises(TypeError):
            claim(location=(18, 22))


class TestIdExcludesLocation:
    """D2: the id is `(reported_value.text, metric, units)` and nothing else."""

    def test_id_is_identical_for_claims_differing_only_in_location(self) -> None:
        """The whole point of D2.

        Aspect 3 merges duplicate locations into one claim and requires the id to
        survive that merge unchanged. If location fed the id, dedup would change
        identity — and identity is what dedup is keyed on.
        """
        first = claim(location=CharSpan(18, 22))
        second = claim(location=CharSpan(404, 408))

        assert first.location != second.location
        assert first.id == second.id

    def test_id_ignores_artifact_hint_and_tolerance_hint(self) -> None:
        """Both are hints about how to check a claim, not about which claim it is."""
        first = claim(artifact_hint="notebooks/eval.ipynb", tolerance_hint=None)
        second = claim(artifact_hint="src/train.py", tolerance_hint="±0.01")

        assert first.id == second.id


class TestIdDistinguishes:
    def test_0_870_and_0_87_are_different_claims(self) -> None:
        """The trap the id exists to avoid, asserted where it can be seen.

        `Decimal("0.870") == Decimal("0.87")` is `True` — `Decimal` compares
        numerically, not representationally. An id derived from the `Decimal` would
        therefore merge two values the paper reported at different precisions. The id
        is derived from the verbatim `text`, which keeps them apart.
        """
        three_figures = value("0.870")
        two_figures = value("0.87")

        assert three_figures.value == two_figures.value  # type: ignore[attr-defined]
        assert three_figures.text != two_figures.text

        assert claim(reported_value=three_figures).id != claim(
            reported_value=two_figures
        ).id

    def test_id_differs_when_metric_differs(self) -> None:
        assert claim(metric="AUC").id != claim(metric="AUPRC").id

    def test_id_differs_when_units_differ(self) -> None:
        assert claim(units="%").id != claim(units="mg/dL").id

    def test_absent_units_differ_from_empty_units(self) -> None:
        """`None` means dimensionless; `""` is a caller who wrote an empty string.

        They must not hash alike, or an absent unit and a blank one become the same
        claim.
        """
        assert claim(units=None).id != claim(units="").id

    def test_id_differs_when_value_kind_differs_at_equal_magnitude(self) -> None:
        """`p < 0.001` and `0.001` are different claims, not one claim twice."""
        bound = claim(metric="p", reported_value=value("p < 0.001"))
        point = claim(metric="p", reported_value=value("0.001"))

        assert bound.id != point.id

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            # Naive concatenation collides: "12" + "3" == "1" + "23".
            (
                {"reported_value": value("12"), "metric": "3", "units": "x"},
                {"reported_value": value("1"), "metric": "23", "units": "x"},
            ),
            # ... and again across the metric/units boundary: "ab" + "c" == "a" + "bc".
            (
                {"metric": "ab", "units": "c"},
                {"metric": "a", "units": "bc"},
            ),
        ],
    )
    def test_fields_that_would_collide_under_naive_concatenation_do_not(
        self, left: dict[str, object], right: dict[str, object]
    ) -> None:
        """Joining the fields with nothing between them would make these one claim."""
        assert claim(**left).id != claim(**right).id


class TestIdShape:
    def test_id_is_stable_across_identical_constructions(self) -> None:
        assert claim().id == claim().id

    def test_id_is_a_sha256_hex_digest(self) -> None:
        claim_id = claim().id

        assert len(claim_id) == 64
        assert set(claim_id) <= set("0123456789abcdef")

    def test_id_cannot_be_supplied_by_the_caller(self) -> None:
        """It is derived, so a caller-supplied id could contradict the fields."""
        with pytest.raises(TypeError):
            claim(id="deadbeef")


class TestNoConfidence:
    def test_claim_has_no_confidence_attribute(self) -> None:
        """A guardrail, not an omission, and not a style check.

        A `confidence: float` on this record becomes `if claim.confidence > 0.9` at
        verdict time. That is a model's opinion deciding whether a claim holds — the
        exact substitution `CLAUDE.md` #1 and `docs/technical/ARCHITECTURE.md:8-10`
        forbid: a model may *propose* a claim or a binding, but only re-execution
        against the real run may assign a verdict.

        The field is also unnecessary. A claim we are not sure about is not a
        low-confidence claim; it is a claim whose verdict is decided by running the
        artifact, and if it cannot be bound or run the honest outcome is `UNVERIFIED`
        with a named cause — which is a fact about the run, not a number on the record.

        If you are here because you want to record how sure an extractor was, that
        signal belongs in the extractor's own output and must not ride on the record
        that the verdict layer reads.
        """
        assert not hasattr(claim(), "confidence")

    def test_confidence_cannot_be_passed_to_the_constructor(self) -> None:
        with pytest.raises(TypeError):
            claim(confidence=0.95)

    def test_confidence_cannot_be_attached_after_construction(self) -> None:
        """Closing the back door: no setting it on an instance either.

        The exception *type* is deliberately not pinned. `Claim` is a frozen dataclass
        with `slots=True`, and CPython's generated `__setattr__` closes over the
        pre-slots class, so assigning an unknown attribute raises a confusing
        `TypeError` from `super()` rather than `FrozenInstanceError` (3.12.13,
        verified). That is an implementation detail of the interpreter and may change;
        the invariant this test defends is the one asserted last — the attribute does
        not exist afterwards.
        """
        c = claim()

        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            c.confidence = 0.95  # type: ignore[attr-defined]

        assert not hasattr(c, "confidence")

    def test_confidence_cannot_be_forced_on_with_object_setattr(self) -> None:
        """`slots=True` is load-bearing here, not a micro-optimisation.

        Without it the record would carry a `__dict__` and
        `object.__setattr__(claim, "confidence", 0.9)` would succeed, giving the field
        a way back in through the side door. With slots there is nowhere to put it.
        """
        c = claim()

        with pytest.raises(AttributeError):
            object.__setattr__(c, "confidence", 0.95)


class TestFrozen:
    @pytest.mark.parametrize(
        ("field", "new_value"),
        [
            ("reported_value", "0.99"),
            ("units", "%"),
            ("metric", "AUPRC"),
            ("location", CharSpan(0, 1)),
            ("artifact_hint", "src/train.py"),
            ("tolerance_hint", "±0.01"),
            ("id", "deadbeef"),
        ],
    )
    def test_fields_cannot_be_reassigned(self, field: str, new_value: object) -> None:
        """A claim is a record of what a paper said; it does not get edited later."""
        c = claim()

        with pytest.raises(FrozenInstanceError):
            setattr(c, field, new_value)

    def test_equal_field_values_make_equal_claims(self) -> None:
        assert claim() == claim()

    def test_claims_differing_in_location_are_not_equal(self) -> None:
        """Unlike the id, equality *does* see location — it compares whole records."""
        assert claim(location=CharSpan(18, 22)) != claim(location=CharSpan(404, 408))


class TestValueDecimalTrapIsReal:
    def test_decimal_equality_ignores_significant_figures(self) -> None:
        """Documents the language behaviour the id design depends on.

        Asserted here rather than assumed, because the rest of this file's reasoning
        collapses if it is ever false.
        """
        assert Decimal("0.870") == Decimal("0.87")
        assert Decimal("0.870").as_tuple() != Decimal("0.87").as_tuple()
