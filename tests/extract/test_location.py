"""Tests for the `Location` union and `normalize_text`.

The load-bearing contract under test: a `CharSpan` holds **character** offsets into
the **normalized** text. Not byte offsets, not offsets into the raw input. C6's paper
hash covers the normalized text, so if these offsets indexed anything else, a
published verdict would point at different content than it was derived from.
"""

from dataclasses import FrozenInstanceError, dataclass
from typing import ClassVar
import unicodedata

import pytest

from plumb.extract.location import CharSpan, Location, normalize_text

# A paragraph carrying a multi-byte character (µ, U+00B5) and a Greek alpha, so that
# a byte-offset implementation cannot pass by accident.
PARAGRAPH = "We report AUC 0.87 for the µ-cohort (α = 0.05) across 12 sites."


def span_of(text: str, needle: str) -> CharSpan:
    """Build the span a correct extractor would emit for `needle` inside `text`."""
    start = text.index(needle)
    return CharSpan(start, start + len(needle))


class TestRoundTrip:
    @pytest.mark.parametrize(
        "needle",
        [
            "We",
            "AUC 0.87",
            "µ-cohort",
            "α = 0.05",
            "12 sites",
            PARAGRAPH,
        ],
    )
    def test_slicing_normalized_text_returns_the_exact_span(self, needle: str) -> None:
        normalized = normalize_text(PARAGRAPH)
        loc = span_of(normalized, needle)

        assert normalized[loc.start : loc.end] == needle

    def test_offsets_are_character_offsets_not_byte_offsets(self) -> None:
        normalized = normalize_text(PARAGRAPH)
        loc = span_of(normalized, "α = 0.05")

        # Two multi-byte characters precede the span, so a byte-indexed reading of the
        # same offsets lands somewhere else entirely. Asserting the mismatch is what
        # makes this a character-offset test rather than a coincidence.
        as_bytes = normalized.encode("utf-8")
        assert len(as_bytes) > len(normalized)
        assert as_bytes[loc.start : loc.end].decode("utf-8", "replace") != "α = 0.05"
        assert normalized[loc.start : loc.end] == "α = 0.05"


class TestNormalizeText:
    def test_crlf_and_lf_twins_produce_identical_text_and_offsets(self) -> None:
        crlf = "Table 1\r\nAUC 0.87\r\nn = 412\r\n"
        lf = "Table 1\nAUC 0.87\nn = 412\n"

        normalized_crlf = normalize_text(crlf)
        normalized_lf = normalize_text(lf)

        assert normalized_crlf == normalized_lf
        assert span_of(normalized_crlf, "n = 412") == span_of(normalized_lf, "n = 412")
        assert "\r" not in normalized_crlf

    def test_decomposed_and_composed_twins_normalize_to_the_same_text(self) -> None:
        decomposed = "café latte cohort"  # e + COMBINING ACUTE ACCENT
        composed = "café latte cohort"  # LATIN SMALL LETTER E WITH ACUTE

        assert decomposed != composed
        assert normalize_text(decomposed) == normalize_text(composed)
        assert normalize_text(decomposed) == composed
        assert span_of(normalize_text(decomposed), "cohort") == span_of(
            normalize_text(composed), "cohort"
        )

    def test_normalizing_twice_equals_normalizing_once(self) -> None:
        raws = [
            PARAGRAPH,
            "Table 1\r\nAUC 0.87\r\n",
            "café latte",
            "",
            "\r\n\r\n",
            "ﬁt the model",  # U+FB01 LATIN SMALL LIGATURE FI — NFC leaves it alone
        ]
        for raw in raws:
            once = normalize_text(raw)
            assert normalize_text(once) == once

    def test_does_exactly_two_things_and_nothing_else(self) -> None:
        # No dehyphenation, no whitespace collapsing, no case folding, no stripping:
        # every one of those would shift offsets away from the hashed text.
        raw = "  Signifi-\ncant  RESULTS \t held up.  "

        assert normalize_text(raw) == raw

    def test_is_exactly_crlf_to_lf_then_nfc(self) -> None:
        raw = "Á\r\nB"

        assert normalize_text(raw) == unicodedata.normalize("NFC", "Á\nB")


class TestUnionShape:
    def test_char_span_is_a_location(self) -> None:
        assert isinstance(CharSpan(0, 3), Location)
        assert issubclass(CharSpan, Location)

    def test_location_is_not_instantiable_on_its_own(self) -> None:
        # `Location` is the union's base, not a variant. A bare `Location` would be a
        # span with no way to resolve it.
        with pytest.raises(TypeError):
            Location()  # type: ignore[abstract]

    def test_variants_carry_a_discriminating_tag(self) -> None:
        # The tag is what lets a future `PageBox` variant join the union without a
        # schema migration.
        assert CharSpan.kind == "char_span"
        assert CharSpan(0, 3).kind == "char_span"

    def test_a_variant_without_a_tag_is_rejected(self) -> None:
        # The whole point of making this a union now is that `PageBox` can join it
        # later. A variant that forgets its tag would be indistinguishable from a
        # `CharSpan` the moment aspect 3 serializes it, so it must not be definable.
        with pytest.raises(TypeError):

            class Untagged(Location):
                def __init__(self) -> None:
                    pass

    def test_spans_are_frozen_hashable_and_compare_by_value(self) -> None:
        loc = CharSpan(4, 9)

        assert loc == CharSpan(4, 9)
        assert loc != CharSpan(4, 10)
        assert len({CharSpan(4, 9), CharSpan(4, 9)}) == 1
        with pytest.raises(Exception):
            loc.start = 5  # type: ignore[misc]


class TestSlotsSealTheRecord:
    """A span must not be able to acquire fields nobody declared.

    This is the same guardrail `Claim` and `ClaimValue` carry, and it needs *two*
    declarations to hold: `slots=True` on the variant **and** `__slots__ = ()` on the
    union base. Either one alone leaves the record open — a base without `__slots__`
    carries a `__dict__` descriptor that every variant inherits, which silently defeats
    the variant's own slots.
    """

    def test_the_union_base_declares_empty_slots(self) -> None:
        """Asserted at the source, because this is where the hole reopens.

        `__slots__ = ()` on an abstract base looks like noise and invites deletion. It
        is not: removing it re-opens every variant of the union at once, including ones
        that correctly declare `slots=True` themselves, and nothing else in the file
        would fail. This test is what makes that deletion loud.
        """
        assert Location.__dict__.get("__slots__") == ()
        assert "__dict__" not in Location.__dict__

    def test_an_attribute_cannot_be_forced_on_with_object_setattr(self) -> None:
        """The check that actually proves slots — `frozen=True` alone would pass.

        On a frozen dataclass *without* slots, ordinary assignment still raises, so a
        `setattr` test cannot tell the two apart. Going through `object.__setattr__`
        bypasses the frozen guard and reaches the real question: is there a `__dict__`
        to put the value in?
        """
        loc = CharSpan(1, 2)

        with pytest.raises(AttributeError):
            object.__setattr__(loc, "confidence", 0.9)

        assert not hasattr(loc, "confidence")

    def test_an_undeclared_attribute_cannot_be_attached(self) -> None:
        """The exception *type* is deliberately not pinned.

        With `slots=True` the generated `__setattr__` closes over the pre-slots class
        object, so assigning an *undeclared* attribute raises a confusing `TypeError`
        from `super()` rather than `FrozenInstanceError` (3.12.13, verified). That is an
        interpreter detail and may change; the invariant defended here is the one
        asserted last.
        """
        loc = CharSpan(1, 2)

        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            loc.confidence = 0.9  # type: ignore[attr-defined]

        assert not hasattr(loc, "confidence")

    def test_a_span_carries_no_instance_dict(self) -> None:
        assert not hasattr(CharSpan(1, 2), "__dict__")

    def test_a_future_variant_declared_the_same_way_is_also_sealed(self) -> None:
        """The reason the base fix matters more than the `CharSpan` fix.

        `Location` exists as a union so a PDF `PageBox` variant can join it later. A
        variant that declares `slots=True` exactly as `CharSpan` does must come out
        sealed; if the base ever loses its own `__slots__`, this fails even though
        the variant did everything right.
        """

        @dataclass(frozen=True, slots=True)
        class PageBoxLike(Location):
            kind: ClassVar[str] = "page_box_like"

            page: int

            def __post_init__(self) -> None:
                pass

        box = PageBoxLike(3)

        assert not hasattr(box, "__dict__")
        with pytest.raises(AttributeError):
            object.__setattr__(box, "confidence", 0.9)


class TestInvalidOffsets:
    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (-1, 5),  # negative start would silently wrap under slicing
            (0, -1),  # negative end would silently truncate
            (-3, -1),
            (9, 4),  # start > end slices to "" — a silently empty span
        ],
    )
    def test_impossible_spans_are_rejected_at_construction(
        self, start: int, end: int
    ) -> None:
        with pytest.raises(ValueError):
            CharSpan(start, end)

    @pytest.mark.parametrize(("start", "end"), [(0.0, 3), (0, 3.5), (True, 3)])
    def test_non_integer_offsets_are_rejected(self, start: object, end: object) -> None:
        with pytest.raises(TypeError):
            CharSpan(start, end)  # type: ignore[arg-type]

    def test_zero_width_span_is_legal(self) -> None:
        loc = CharSpan(7, 7)

        assert normalize_text(PARAGRAPH)[loc.start : loc.end] == ""
