"""Tests for the ordering contract shared by `dedup.py` and `serialize.py`.

These assertions are made on the order keys themselves, with every other component
held equal. A test that observes only a module's *output* cannot distinguish "this key
component is total" from "some later component separated them anyway" — and both
consumers have exactly that hazard, since each key ends in a backstop that separates
almost anything.

The keys are the determinism contract, and the contract now has one implementation
that two modules import. That is why these tests live here rather than in either
consumer's file: a key that came out right *through dedup's output* was never evidence
about the key, and it is not evidence about serialization either.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from plumb.extract.claim import Claim
from plumb.extract.dedup import group_claims
from plumb.extract.location import CharSpan, Location
from plumb.extract.ordering import (
    identity_sort_key,
    location_sort_key,
    member_sort_key,
    optional_sort_key,
)
from plumb.extract.value import ClaimValue, parse_value


def value(text: str) -> ClaimValue:
    """`parse_value` that fails the test rather than returning `None` into a fixture."""
    parsed = parse_value(text)
    assert parsed is not None, f"fixture text did not parse: {text!r}"
    return parsed


def claim(**overrides: object) -> Claim:
    """A fully-specified `Claim`, with named fields replaced per test."""
    fields: dict[str, object] = {
        "reported_value": value("0.87"),
        "units": None,
        "metric": "AUC",
        "location": CharSpan(18, 22),
        "artifact_hint": None,
        "tolerance_hint": None,
    }
    fields.update(overrides)
    return Claim(**fields)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class PageBox(Location):
    """A plausible future `Location` variant, not yet registered."""

    kind: ClassVar[str] = "page_box"

    page: int = 1


class TestOptionalSortKey:
    """`None` and `""` are different facts, and the key must keep them apart."""

    def test_optional_key_separates_none_from_empty_string(self) -> None:
        """The whole defect in one line: `None or ""` is `""`."""
        assert optional_sort_key(None) != optional_sort_key("")

    def test_optional_key_orders_none_before_any_string(self) -> None:
        for present in ("", "a", "±0.01", "\x00"):
            assert optional_sort_key(None) < optional_sort_key(present)

    def test_units_presence_sorts_before_units_value(self) -> None:
        # `None` must not simply sort where `""` would; it occupies its own position,
        # ahead of every present value including the empty one. The second assertion
        # is the one the first does not make: present values still order among
        # themselves, rather than all collapsing into one "present" bucket.
        assert optional_sort_key(None) < optional_sort_key("")
        assert optional_sort_key("") < optional_sort_key("mg/L")


class TestLocationSortKey:
    """The variant tag leads; an unorderable variant is refused rather than guessed."""

    def test_the_location_key_leads_with_the_variant_tag(self) -> None:
        # D2 keys on `location.start`/`location.end`, which live on `CharSpan` and not
        # on the `Location` base the union is built around. With the tag leading, a
        # second variant orders against `CharSpan` instead of colliding with it — a
        # `PageBox` given a `start` "for convenience" would otherwise sort page numbers
        # against character offsets, silently, while the suite stayed green.
        assert location_sort_key(CharSpan(start=3, end=7)) == ("char_span", 3, 7)
        assert location_sort_key(CharSpan(start=3, end=7))[0] == CharSpan.kind

    def test_an_unordered_location_variant_raises_and_names_the_extension_point(
        self,
    ) -> None:
        with pytest.raises(TypeError, match="location_sort_key"):
            location_sort_key(PageBox())


class TestIdentityAndMemberKeys:
    """Assertions on the order keys themselves, with every other component held equal.

    The member key has the hazard this class is shaped around: `artifact_hint` is
    followed by `tolerance_hint`, so a fixture whose tolerance hints differ would pass
    while the artifact-hint component was broken. These tests hold the backstop equal
    so only the component under test can decide the order.
    """

    def test_identity_key_separates_none_units_from_empty_units(self) -> None:
        """Units is the last component of the identity key, so nothing can mask it."""
        assert identity_sort_key(("0.87", "AUC", None)) != identity_sort_key(
            ("0.87", "AUC", "")
        )

    def test_member_key_separates_hints_with_the_backstop_held_equal(self) -> None:
        """`artifact_hint` must decide on its own, not with `tolerance_hint`'s help."""
        absent = claim(artifact_hint=None, tolerance_hint=None)
        empty = claim(artifact_hint="", tolerance_hint=None)

        assert absent.location == empty.location
        assert absent.tolerance_hint == empty.tolerance_hint
        assert member_sort_key(absent) != member_sort_key(empty)

    def test_member_key_separates_tolerance_hints_with_earlier_parts_equal(
        self,
    ) -> None:
        absent = claim(artifact_hint=None, tolerance_hint=None)
        empty = claim(artifact_hint=None, tolerance_hint="")

        assert member_sort_key(absent) != member_sort_key(empty)

    def test_no_two_members_of_a_group_share_a_member_key(self) -> None:
        """Totality as a property, over every axis a group member may vary on.

        A shared key between two distinct members is the tie that hands ordering back
        to input order — the failure this whole class exists to make visible.
        """
        members = [
            claim(location=CharSpan(18, 22), artifact_hint=None, tolerance_hint=None),
            claim(location=CharSpan(18, 22), artifact_hint="", tolerance_hint=None),
            claim(location=CharSpan(18, 22), artifact_hint=None, tolerance_hint=""),
            claim(location=CharSpan(18, 22), artifact_hint="a", tolerance_hint=None),
            claim(location=CharSpan(18, 30), artifact_hint=None, tolerance_hint=None),
            claim(location=CharSpan(404, 408), artifact_hint=None, tolerance_hint=None),
        ]

        keys = [member_sort_key(member) for member in members]

        assert len(keys) == len(set(keys))

    def test_member_ordering_is_input_independent_for_none_versus_empty_hint(
        self,
    ) -> None:
        """The behavioural half, with the backstop held equal so it cannot help."""
        absent = claim(artifact_hint=None, tolerance_hint=None)
        empty = claim(artifact_hint="", tolerance_hint=None)

        assert group_claims([absent, empty]) == group_claims([empty, absent])
