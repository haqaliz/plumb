"""The decision: does the re-derived value hold the paper's claim? (M3; D1–D4, D7)

`decide` is pure `Decimal` arithmetic over a reported `ClaimValue` and one
located value. The rules pinned here are the R2 surface — each one exists so
that a number the run agrees with is never reported as `DIVERGED`:

- **D1** a reported number stands for its written precision: `0.87` is the closed
  band `[0.865, 0.875]`, and a value inside it is `REPRODUCED`.
- **D1a** a round integer (`10,000`) has no readable precision →
  `PRECISION_AMBIGUOUS` unless the binding gives a tolerance.
- **D2** outside the band, only an explicit tolerance makes `WITHIN-TOLERANCE`;
  otherwise the paper's own precision was the tolerance, and it is `DIVERGED`.
- **D3** only `Point` and `Bound` are compared.
- **D4** a percent claim must declare the artifact's scale.
- **D7** an artifact that wrote fewer digits than the paper, and agrees at its
  own precision, cannot decide the claim → `ARTIFACT_PRECISION_COARSER`.

Reported values are built with C1's own `parse_value`, so they carry real
paper-shaped text and exponents.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from plumb.extract.value import parse_value
from plumb.verify import causes
from plumb.verify.compare import (
    DIVERGED,
    REPRODUCED,
    UNVERIFIED,
    WITHIN_TOLERANCE,
    Decision,
    decide,
)
from plumb.verify.numbers import Tolerance, half_unit

D = Decimal


def run(
    reported: str,
    located: str,
    *,
    units: str | None = None,
    tolerance: tuple[str, str] | None = None,
    scale: str | None = None,
) -> Decision:
    value = parse_value(reported)
    assert value is not None, reported
    return decide(
        value,
        units,
        D(located),
        half_unit(D(located)),
        None if tolerance is None else Tolerance(tolerance[0], D(tolerance[1])),
        None if scale is None else D(scale),
    )


def verdict(decision: Decision) -> str:
    return decision.cause if decision.verdict == UNVERIFIED else decision.verdict


class TestGates:
    @pytest.mark.parametrize(
        "reported", ["0.85 ± 0.03", "95% CI [0.81, 0.89]", "12–15%", "~10,000"]
    )
    def test_value_kinds_this_slice_does_not_compare(self, reported: str) -> None:
        decision = run(reported, "0.85")
        assert decision.verdict == UNVERIFIED
        assert decision.cause == causes.UNSUPPORTED_VALUE_KIND

    def test_a_percent_in_the_text_without_a_scale_is_unit_undeclared(self) -> None:
        assert verdict(run("87%", "0.87")) == causes.UNIT_UNDECLARED

    def test_percent_units_without_a_scale_are_unit_undeclared(self) -> None:
        assert verdict(run("87", "0.87", units="%")) == causes.UNIT_UNDECLARED

    def test_a_declared_scale_is_applied_before_comparing(self) -> None:
        decision = run("87%", "0.8712", scale="100")
        assert decision.verdict == REPRODUCED
        assert decision.rederived == D("87.1200")

    def test_a_scale_of_one_declares_the_artifact_already_in_percent(self) -> None:
        assert run("87%", "87.1", scale="1").verdict == REPRODUCED

    def test_a_scale_is_allowed_on_any_claim(self) -> None:
        assert run("251", "0.2512", scale="1000").verdict == REPRODUCED

    @pytest.mark.parametrize("field", ["located", "half_unit", "scale"])
    def test_a_float_anywhere_is_refused(self, field: str) -> None:
        args = {"located": D("0.87"), "half_unit": D("0.005"), "scale": None}
        args[field] = 0.87
        with pytest.raises(TypeError):
            decide(parse_value("0.87"), None, args["located"], args["half_unit"], None,
                   args["scale"])


class TestPointBand:
    def test_an_exact_match_is_reproduced_with_zero_delta(self) -> None:
        decision = run("0.87", "0.87")
        assert decision.verdict == REPRODUCED
        assert decision.cause is None
        assert decision.delta == 0
        assert decision.band == (D("0.865"), D("0.875"))

    def test_a_value_inside_the_written_precision_is_reproduced(self) -> None:
        decision = run("0.87", "0.8712")
        assert decision.verdict == REPRODUCED
        assert decision.band == (D("0.865"), D("0.875"))
        assert decision.delta == D("0.0012")

    def test_the_band_is_closed_at_the_boundary(self) -> None:
        assert run("0.87", "0.875").verdict == REPRODUCED
        assert run("0.87", "0.865").verdict == REPRODUCED

    def test_just_outside_the_band_is_diverged(self) -> None:
        decision = run("0.87", "0.8751")
        assert decision.verdict == DIVERGED
        assert decision.cause is None
        assert decision.delta == D("0.0051")

    def test_the_precision_the_paper_wrote_is_honoured(self) -> None:
        # 0.870 claims three places: ±0.0005, so 0.8712 does not hold it.
        assert run("0.870", "0.8712").verdict == DIVERGED

    def test_negative_values_have_a_symmetric_band(self) -> None:
        assert run("-2.25", "-2.254").verdict == REPRODUCED
        assert run("-2.25", "-2.256").verdict == DIVERGED

    def test_scientific_notation_states_its_precision(self) -> None:
        assert run("1.5e3", "1520").verdict == REPRODUCED
        assert run("1.5e3", "1560").verdict == DIVERGED


class TestPointTolerance:
    def test_inside_an_absolute_tolerance_is_within_tolerance(self) -> None:
        decision = run("0.87", "0.89", tolerance=("abs", "0.05"))
        assert decision.verdict == WITHIN_TOLERANCE
        assert decision.tolerance_band == (D("0.82"), D("0.92"))
        assert decision.band == (D("0.865"), D("0.875"))

    def test_outside_a_relative_tolerance_is_diverged(self) -> None:
        decision = run("0.87", "0.89", tolerance=("rel", "0.01"))
        assert decision.verdict == DIVERGED
        assert decision.tolerance_band == (D("0.8613"), D("0.8787"))

    def test_a_relative_tolerance_scales_with_the_magnitude(self) -> None:
        assert run("-40.0", "-41.5", tolerance=("rel", "0.05")).verdict == WITHIN_TOLERANCE

    def test_a_relative_tolerance_against_zero_is_no_tolerance(self) -> None:
        assert verdict(run("0", "0.7", tolerance=("rel", "0.1"))) == causes.NO_TOLERANCE

    def test_a_zero_tolerance_adds_nothing(self) -> None:
        assert run("0.87", "0.88", tolerance=("abs", "0")).verdict == DIVERGED

    def test_inside_the_band_needs_no_tolerance(self) -> None:
        assert run("0.87", "0.871", tolerance=("abs", "0.05")).verdict == REPRODUCED


class TestRoundIntegers:
    @pytest.mark.parametrize("reported", ["10,000", "20", "300"])
    def test_a_round_integer_without_tolerance_is_precision_ambiguous(
        self, reported: str
    ) -> None:
        decision = run(reported, "10213")
        assert decision.verdict == UNVERIFIED
        assert decision.cause == causes.PRECISION_AMBIGUOUS
        assert decision.rederived == D("10213")

    def test_with_a_tolerance_it_is_decided(self) -> None:
        assert run("10,000", "10213", tolerance=("abs", "500")).verdict == WITHIN_TOLERANCE

    def test_an_integer_not_ending_in_zero_is_exact(self) -> None:
        assert run("12", "12.4").verdict == REPRODUCED
        assert run("12", "12.6").verdict == DIVERGED

    def test_a_written_decimal_place_is_not_ambiguous(self) -> None:
        assert run("100.0", "100.3").verdict == DIVERGED

    def test_zero_is_not_ambiguous(self) -> None:
        assert run("0", "0.2").verdict == REPRODUCED


class TestCoarseArtifact:
    def test_an_artifact_coarser_than_the_paper_that_agrees_is_undecidable(self) -> None:
        decision = run("0.8712", "0.87")
        assert decision.verdict == UNVERIFIED
        assert decision.cause == causes.ARTIFACT_PRECISION_COARSER
        assert decision.rederived == D("0.87")

    def test_an_artifact_coarser_than_the_paper_that_disagrees_is_diverged(self) -> None:
        assert run("0.8712", "0.89").verdict == DIVERGED

    def test_the_scaled_exponent_trap(self) -> None:
        # 0.87 × 100 is Decimal("87.00") — exponent −2 — but the artifact wrote two
        # places of a fraction, i.e. whole percent: its half-unit is 0.5, not 0.005.
        assert verdict(run("87.12%", "0.87", scale="100")) == causes.ARTIFACT_PRECISION_COARSER

    def test_coarseness_comes_before_tolerance(self) -> None:
        decision = run("0.8712", "0.87", tolerance=("abs", "0.01"))
        assert decision.cause == causes.ARTIFACT_PRECISION_COARSER

    def test_an_equally_precise_artifact_is_not_coarse(self) -> None:
        assert run("0.87", "0.89").verdict == DIVERGED
