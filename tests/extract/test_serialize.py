"""Tests for the serialized form — the contract C6 bundles and a third party replays.

The load-bearing property is byte-identity: the same claims and the same paper hash
produce the same bytes, forever. Every assertion here is therefore made on `bytes`;
asserting on `str` would leave the encoding unpinned and let the one thing being
promised go unchecked.

Three traps get their own sections, because each one passes a casual test while
breaking the contract:

- **A float at the last moment.** `Decimal` is not JSON-serializable and the reflex
  fix is `default=float`. That reintroduces R2 (`docs/ROADMAP.md:57`) after the whole
  record layer spent its effort keeping it out, so `TestNoFloatEverReachesTheOutput`
  parses the output back with a hook that fails on any JSON float literal.
- **An order that is not total.** `sorted()` is stable, but stability only preserves
  an input order that may itself be nondeterministic. `TestOrdering` shuffles.
- **A collapsed distinction.** `units=None` and `units=""` are different facts that
  aspect 1's `id` already distinguishes; serialization must not fuse them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from typing import Any, ClassVar

import pytest

from plumb.extract.claim import Claim
from plumb.extract.hashing import PaperHash, hash_paper
from plumb.extract.location import CharSpan, Location
from plumb.extract.serialize import (
    SERIALIZATION,
    _order_key,
    serialize_claims,
)
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

PAPER = "We report AUC 0.87 for the µ-cohort.\n"
PAPER_HASH = hash_paper(PAPER)


def claim(
    text: str = "0.87",
    *,
    metric: str = "AUC",
    units: str | None = None,
    start: int = 14,
    end: int = 18,
    artifact_hint: str | None = None,
    tolerance_hint: str | None = None,
) -> Claim:
    """A claim built from a parsed value, so the tests exercise real parser output."""
    value = parse_value(text)
    assert value is not None, f"fixture value must parse: {text!r}"
    return Claim(
        reported_value=value,
        units=units,
        metric=metric,
        location=CharSpan(start=start, end=end),
        artifact_hint=artifact_hint,
        tolerance_hint=tolerance_hint,
    )


def serialized(*claims: Claim, paper_hash: PaperHash = PAPER_HASH) -> bytes:
    return serialize_claims(list(claims), paper_hash=paper_hash)


def document(*claims: Claim, paper_hash: PaperHash = PAPER_HASH) -> Any:
    """The output, parsed back — for assertions about structure rather than bytes."""
    return json.loads(serialized(*claims, paper_hash=paper_hash).decode("utf-8"))


class TestByteIdentity:
    """Same input, same bytes — asserted on bytes, never on str."""

    def test_same_input_twice_in_one_process_is_byte_identical(self) -> None:
        first = serialized(claim(), claim("0.91", metric="F1"))
        second = serialized(claim(), claim("0.91", metric="F1"))
        assert first == second

    def test_equal_but_distinct_records_serialize_identically(self) -> None:
        # Byte-identity must follow from the *values*, never from object identity.
        assert serialized(claim()) == serialized(claim())

    def test_output_is_bytes_not_str(self) -> None:
        assert isinstance(serialized(claim()), bytes)

    def test_output_is_valid_utf8(self) -> None:
        serialized(claim("0.87", metric="µ-cohort AUC")).decode("utf-8")

    def test_output_ends_with_exactly_one_newline(self) -> None:
        out = serialized(claim())
        assert out.endswith(b"\n")
        assert not out.endswith(b"\n\n")
        # `indent=None` too: the document is one line plus the terminator.
        assert out.count(b"\n") == 1

    def test_a_different_paper_hash_changes_the_bytes(self) -> None:
        other = hash_paper(PAPER + "One more sentence.\n")
        assert serialized(claim()) != serialized(claim(), paper_hash=other)


class TestEmptyInput:
    """An empty claim list is a document that says so, not an empty file."""

    def test_empty_claims_serialize_to_a_non_empty_document(self) -> None:
        out = serialized()
        assert out != b""
        assert out.endswith(b"\n")

    def test_empty_claims_serialize_to_valid_json_with_an_empty_claim_list(self) -> None:
        assert document()["claims"] == []

    def test_empty_claims_are_stable(self) -> None:
        assert serialized() == serialized()


class TestPaperHashIsRecordedWithItsAlgorithm:
    """A digest is uninterpretable without the function that produced it."""

    def test_the_algorithm_name_appears_in_the_output(self) -> None:
        assert b"sha256" in serialized(claim())

    def test_digest_and_algorithm_appear_together(self) -> None:
        recorded = document(claim())["paper_hash"]
        assert recorded["digest"] == PAPER_HASH.digest
        assert recorded["algorithm"] == PAPER_HASH.algorithm

    def test_a_bare_hex_string_is_refused(self) -> None:
        # The serializer must not be able to stamp an algorithm onto a digest it did
        # not produce; taking the record rather than a string makes that impossible.
        with pytest.raises(TypeError):
            serialize_claims([claim()], paper_hash=PAPER_HASH.digest)  # type: ignore[arg-type]

    def test_the_algorithm_is_not_a_parameter(self) -> None:
        # Parameterizing it would turn "identical input -> identical bytes" into
        # "identical input *and callers who agree* -> identical bytes".
        import inspect

        params = inspect.signature(serialize_claims).parameters
        assert set(params) == {"claims", "paper_hash"}


class TestPinnedJsonOptions:
    """Every option is stated in one place; a reader should not have to infer it."""

    def test_the_options_are_pinned_on_a_named_constant(self) -> None:
        assert SERIALIZATION.sort_keys is True
        assert SERIALIZATION.ensure_ascii is False
        assert SERIALIZATION.separators == (",", ":")
        assert SERIALIZATION.indent is None
        assert SERIALIZATION.encoding == "utf-8"
        assert SERIALIZATION.trailing_newline == "\n"

    def test_keys_are_sorted(self) -> None:
        out = serialized(claim()).decode("utf-8")
        assert out.index('"claims"') < out.index('"paper_hash"')
        first = document(claim())["claims"][0]
        assert list(first) == sorted(first)

    def test_separators_carry_no_whitespace(self) -> None:
        out = serialized(claim())
        assert b", " not in out
        assert b": " not in out

    def test_non_ascii_survives_literally(self) -> None:
        # é (U+00E9), en dash (U+2013), µ (U+00B5): `ensure_ascii=False` keeps them
        # as themselves rather than as \\u escapes.
        out = serialized(
            claim("12–15%", metric="café coverage", units="µg"),
        )
        assert "café".encode("utf-8") in out
        assert "–".encode("utf-8") in out
        assert "µ".encode("utf-8") in out
        assert rb"\u" not in out


class TestSignificantFiguresSurvive:
    """`Decimal("0.870") == Decimal("0.87")` is True; the bytes must not agree."""

    def test_trailing_zero_changes_the_bytes(self) -> None:
        assert serialized(claim("0.870")) != serialized(claim("0.87"))

    def test_leading_zero_changes_the_bytes(self) -> None:
        # Per the plan's §0: `.87` and `0.87` are two claims, not one.
        assert serialized(claim(".87")) != serialized(claim("0.87"))

    def test_the_verbatim_text_is_carried_through(self) -> None:
        assert '"0.870"'.encode("utf-8") in serialized(claim("0.870"))


class TestUnitsDistinction:
    """`None` (dimensionless) and `""` (a caller who wrote an empty string) differ."""

    def test_none_and_empty_string_serialize_distinguishably(self) -> None:
        assert serialized(claim(units=None)) != serialized(claim(units=""))

    def test_none_serializes_as_null_not_as_empty_string(self) -> None:
        assert document(claim(units=None))["claims"][0]["units"] is None
        assert document(claim(units=""))["claims"][0]["units"] == ""


class TestOrdering:
    """A total key, applied to an input whose own order proves nothing."""

    def test_input_order_does_not_change_the_output(self) -> None:
        a = claim("0.87", metric="AUC")
        b = claim("0.91", metric="F1", start=40, end=44)
        c = claim("0.87", metric="AUC", start=90, end=94)
        assert serialize_claims([a, b, c], paper_hash=PAPER_HASH) == serialize_claims(
            [c, b, a], paper_hash=PAPER_HASH
        )

    def test_order_follows_the_declared_key(self) -> None:
        # (reported_value.text, metric, units or "", location.start, location.end)
        low_text = claim("0.12", metric="zzz", start=99, end=103)
        high_text = claim("0.99", metric="aaa", start=0, end=4)
        out = document(high_text, low_text)["claims"]
        assert [c["reported_value"]["text"] for c in out] == ["0.12", "0.99"]

    def test_location_breaks_a_tie_on_value_and_metric(self) -> None:
        late = claim(start=90, end=94)
        early = claim(start=14, end=18)
        out = document(late, early)["claims"]
        assert [c["location"]["start"] for c in out] == [14, 90]

    def test_claims_alike_but_for_units_presence_have_a_stable_relative_order(
        self,
    ) -> None:
        # The declared key's `units or ""` maps None and "" to one sort value, so this
        # pair has no defined relative order under it — the exact nondeterminism this
        # phase removes. Presence sorts separately from value: `None` first.
        none_units = claim(units=None)
        empty_units = claim(units="")
        forwards = serialize_claims([none_units, empty_units], paper_hash=PAPER_HASH)
        backwards = serialize_claims([empty_units, none_units], paper_hash=PAPER_HASH)
        assert forwards == backwards
        ordered = json.loads(forwards.decode("utf-8"))["claims"]
        assert [c["units"] for c in ordered] == [None, ""]

    def test_the_order_key_itself_distinguishes_units_presence(self) -> None:
        # Asserted on the key, holding the final backstop component equal, because the
        # emitted order alone does not prove this: with `units or ""` the two claims
        # tie through every declared component and the canonical-encoding backstop
        # still separates them — by their ids, which is an arbitrary order that can
        # happen to look right. This assertion is the one that fails without it.
        none_units = _order_key(claim(units=None), "same-canonical")
        empty_units = _order_key(claim(units=""), "same-canonical")
        assert none_units != empty_units
        assert none_units < empty_units

    def test_claims_alike_but_for_hints_are_ordered_deterministically(self) -> None:
        # Identical in every field of the declared key *and* in `id`, differing only
        # in a hint. Still must not depend on input order.
        with_hint = claim(artifact_hint="results/table2.csv")
        without_hint = claim(artifact_hint=None)
        assert serialize_claims(
            [with_hint, without_hint], paper_hash=PAPER_HASH
        ) == serialize_claims([without_hint, with_hint], paper_hash=PAPER_HASH)

    def test_identical_claims_both_appear(self) -> None:
        # Serialization does not dedup; that is aspect 3's Phase 3, not this function.
        assert len(document(claim(), claim())["claims"]) == 2

    def test_an_iterator_is_accepted_and_ordered(self) -> None:
        claims = [claim("0.91", metric="F1"), claim("0.87", metric="AUC")]
        assert serialize_claims(iter(claims), paper_hash=PAPER_HASH) == serialize_claims(
            claims, paper_hash=PAPER_HASH
        )


def _fail_on_float(literal: str) -> float:
    raise AssertionError(
        f"a JSON float literal reached the output: {literal!r} — a Decimal was "
        "coerced through float somewhere"
    )


class TestNoFloatEverReachesTheOutput:
    """Every `Decimal` leaves as its verbatim text, in every variant."""

    @pytest.mark.parametrize(
        "text",
        [
            "0.87",  # Point
            "p < 0.001",  # Bound
            "0.85 ± 0.03",  # PlusMinus
            "95% CI [0.81, 0.89]",  # Interval
            "12–15%",  # Range
            "~10,000",  # Approximate
        ],
    )
    def test_no_json_float_literal_for_any_variant(self, text: str) -> None:
        out = serialized(claim(text))
        # `parse_float` fires on any JSON number carrying a `.` or an exponent.
        json.loads(out.decode("utf-8"), parse_float=_fail_on_float)

    def test_every_variant_is_covered_by_the_parametrization(self) -> None:
        # A new variant must not slip in unserialized — the guard above only guards
        # what it is handed.
        variants = {
            type(parse_value(t))
            for t in (
                "0.87",
                "p < 0.001",
                "0.85 ± 0.03",
                "95% CI [0.81, 0.89]",
                "12–15%",
                "~10,000",
            )
        }
        assert variants == {Point, Bound, PlusMinus, Interval, Range, Approximate}

    def test_decimal_components_are_strings_not_numbers(self) -> None:
        value = document(claim("0.85 ± 0.03"))["claims"][0]["reported_value"]
        assert value["center"] == "0.85"
        assert value["margin"] == "0.03"

    def test_a_decimal_with_a_trailing_zero_keeps_it_in_its_component(self) -> None:
        assert document(claim("0.870"))["claims"][0]["reported_value"]["value"] == "0.870"

    def test_integer_offsets_are_still_json_integers(self) -> None:
        location = document(claim(start=3, end=7))["claims"][0]["location"]
        assert location["start"] == 3 and isinstance(location["start"], int)


@dataclass(frozen=True, slots=True)
class UnknownValue(ClaimValue):
    """A `ClaimValue` variant the serializer has never been told about."""

    weight: Decimal = Decimal("1")


@dataclass(frozen=True, slots=True)
class PageBox(Location):
    """A plausible future `Location` variant, not yet registered."""

    kind: ClassVar[str] = "page_box"

    page: int = 1


class TestTheEncoderRefusesRatherThanCoerces:
    """A fallback that "just works" is how a float gets in."""

    def test_an_unregistered_value_variant_raises(self) -> None:
        rogue = Claim(
            reported_value=UnknownValue(text="0.87"),
            units=None,
            metric="AUC",
            location=CharSpan(start=0, end=4),
            artifact_hint=None,
            tolerance_hint=None,
        )
        with pytest.raises(TypeError):
            serialize_claims([rogue], paper_hash=PAPER_HASH)

    def test_an_unregistered_location_variant_raises(self) -> None:
        rogue = Claim(
            reported_value=Point(text="0.87", value=Decimal("0.87")),
            units=None,
            metric="AUC",
            location=PageBox(),
            artifact_hint=None,
            tolerance_hint=None,
        )
        with pytest.raises(TypeError):
            serialize_claims([rogue], paper_hash=PAPER_HASH)

    def test_a_non_claim_raises(self) -> None:
        with pytest.raises(TypeError):
            serialize_claims(["0.87"], paper_hash=PAPER_HASH)  # type: ignore[list-item]

    def test_the_refusal_names_the_type(self) -> None:
        with pytest.raises(TypeError, match="UnknownValue"):
            serialize_claims(
                [
                    Claim(
                        reported_value=UnknownValue(text="0.87"),
                        units=None,
                        metric="AUC",
                        location=CharSpan(start=0, end=4),
                        artifact_hint=None,
                        tolerance_hint=None,
                    )
                ],
                paper_hash=PAPER_HASH,
            )


class TestNoAmbientState:
    """Determinism comes from not having sources of nondeterminism (D1).

    The AST guards that used to live here — one on imports, one on calls — have been
    deleted rather than kept alongside the repo-wide scan in `test_determinism.py`.
    That scan already reads every module under `src/plumb/extract/`, this one included,
    with a strict superset of their checks: the same import denylist plus an
    *allowlist*, and a name scan that matches a forbidden builtin **referenced as a
    value**, not merely called. The difference is not academic — `json.dumps(
    default=float)` contains no call node at all, so the Call-only version here could
    never have seen it.

    Two guards of unequal strength, with the weaker one sitting closer to the code it
    guards, is worse than one: the next reader finds a local ambient-state test, trusts
    it, and never learns that the coverage that actually holds lives elsewhere.

    What remains is the assertion on the serialized bytes, which is about output rather
    than source and is duplicated nowhere.
    """

    def test_no_timestamp_shaped_or_path_shaped_content_in_the_output(self) -> None:
        out = serialized(claim())
        assert b"20" + b"26-" not in out  # a bare ISO date
        assert b"/Users" not in out
        assert b"/private" not in out


class TestRecordFieldsAreCarried:
    """Nothing on the record is silently dropped on the way out."""

    def test_all_claim_fields_appear(self) -> None:
        one = document(
            claim(
                units="mg/L",
                artifact_hint="results/table2.csv",
                tolerance_hint="within 1%",
            )
        )["claims"][0]
        assert set(one) == {
            "artifact_hint",
            "id",
            "location",
            "metric",
            "reported_value",
            "tolerance_hint",
            "units",
        }

    def test_the_derived_id_is_carried(self) -> None:
        one = claim()
        assert document(one)["claims"][0]["id"] == one.id

    def test_the_location_carries_its_kind_tag(self) -> None:
        location = document(claim())["claims"][0]["location"]
        assert location["kind"] == CharSpan.kind

    def test_the_value_carries_a_kind_tag(self) -> None:
        # Without a tag, `Interval` and `Range` are indistinguishable once serialized:
        # both are a text plus a low and a high.
        interval = document(claim("95% CI [0.81, 0.89]"))["claims"][0]["reported_value"]
        span = document(claim("12–15%"))["claims"][0]["reported_value"]
        assert interval["kind"] != span["kind"]
