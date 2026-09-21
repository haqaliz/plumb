"""Tests for the paper content hash.

The load-bearing contract: the digest covers the **normalized** text — byte-for-byte
the same text a `CharSpan`'s offsets index. If it covered the raw input instead, a
published verdict would be anchored to different content than its own citations point
at, and the same paper checked out on Windows and on macOS would hash differently.

The second contract is that a digest never travels without its algorithm. A digest is
uninterpretable on its own, and a digest that reaches a serializer from elsewhere and
gets stamped `"sha256"` is *mislabeled* — worse than unlabeled, because a replayer is
told how to verify it and the instruction is wrong. So `hash_paper` returns a record
carrying both, and `TestInseparability` pins that there is no path to a bare digest.
"""

from dataclasses import FrozenInstanceError
import hashlib
import inspect

import pytest

from plumb.extract import hashing
from plumb.extract.hashing import PAPER_HASH_ALGORITHM, PaperHash, hash_paper
from plumb.extract.location import normalize_text

# Carries a multi-byte character (µ, U+00B5) so an implementation that hashed the
# wrong encoding cannot pass by accident.
PAPER_LF = "We report AUC 0.87\nfor the µ-cohort.\nAcross 12 sites.\n"
PAPER_CRLF = PAPER_LF.replace("\n", "\r\n")

# `café`, composed (U+00E9) and decomposed (e + U+0301). Different characters, the
# same text after NFC.
CAFE_NFC = "The café cohort reported 0.87."
CAFE_NFD = "The café cohort reported 0.87."


def digest_of(text: str) -> str:
    """The hex digest alone, for the assertions that are about the digest itself."""
    return hash_paper(text).digest


class TestNormalizationBoundary:
    """What must and must not change the digest."""

    def test_crlf_and_lf_twins_hash_identically(self) -> None:
        # A Windows checkout and a macOS checkout of one paper are one paper. Asserted
        # on the whole record, which is strictly stronger than on the digest alone.
        assert PAPER_CRLF != PAPER_LF
        assert hash_paper(PAPER_CRLF) == hash_paper(PAPER_LF)

    def test_nfd_and_nfc_twins_hash_identically(self) -> None:
        # `normalize_text` applies NFC, so a composed é and its decomposed twin are
        # one character in the offsets and must be one paper in the digest.
        assert CAFE_NFD != CAFE_NFC
        assert hash_paper(CAFE_NFD) == hash_paper(CAFE_NFC)

    def test_the_digest_covers_the_normalized_text_not_the_raw_input(self) -> None:
        # Stated directly rather than inferred from the twin tests: whatever the
        # digest is, it is the digest of the normalized form.
        assert hash_paper(PAPER_CRLF) == hash_paper(normalize_text(PAPER_CRLF))

    @pytest.mark.parametrize(
        "changed",
        [
            "We report AUC 0.88\nfor the µ-cohort.\nAcross 12 sites.\n",  # a digit
            "We report AUC 0.87\nfor the u-cohort.\nAcross 12 sites.\n",  # µ -> u
            "We report AUC 0.87\nfor the µ-cohort.\nAcross 12 sites. ",  # trailing ws
            "We report AUC 0.87\nfor the µ-cohort.\nAcross 12 sites.",  # no newline
        ],
    )
    def test_a_single_character_change_changes_the_hash(self, changed: str) -> None:
        assert changed != PAPER_LF
        assert digest_of(changed) != digest_of(PAPER_LF)

    def test_a_lone_carriage_return_is_not_normalized_away(self) -> None:
        # `normalize_text` rewrites CRLF only, by design (location.py). The hash
        # inherits that boundary exactly; it must not run a normalization of its own.
        assert digest_of("a\rb") != digest_of("a\nb")

    def test_empty_text_still_yields_a_full_digest(self) -> None:
        # An empty paper is a paper we can still name. No special case, no empty
        # string, no None.
        expected = hashlib.new(PAPER_HASH_ALGORITHM).digest_size * 2
        assert len(digest_of("")) == expected


class TestRecordedAlgorithm:
    """The algorithm is exposed, and the digest it produces matches what it names."""

    def test_the_algorithm_name_is_exported(self) -> None:
        assert PAPER_HASH_ALGORITHM == "sha256"

    def test_the_record_carries_the_exported_constant(self) -> None:
        # One source of truth. The record reports the constant rather than a second
        # literal that could drift away from it.
        assert hash_paper(PAPER_LF).algorithm == PAPER_HASH_ALGORITHM

    def test_the_digest_length_matches_the_algorithm_the_record_names(self) -> None:
        # Tied to the record's own claim about itself: a record that named an
        # algorithm inconsistent with its digest would fail here.
        result = hash_paper(PAPER_LF)
        expected = hashlib.new(result.algorithm).digest_size * 2

        assert len(result.digest) == expected == 64

    def test_the_digest_is_untruncated_lowercase_hex(self) -> None:
        assert set(digest_of(PAPER_LF)) <= set("0123456789abcdef")


class TestInseparability:
    """There is no path that yields a digest with no algorithm attached."""

    def test_hash_paper_returns_the_record_not_a_bare_string(self) -> None:
        result = hash_paper(PAPER_LF)

        assert isinstance(result, PaperHash)
        # A `str` subclass carrying an `.algorithm` would technically satisfy the
        # attribute checks while still being a bare string everywhere it is passed.
        assert not isinstance(result, str)

    def test_no_public_function_hands_back_a_bare_digest(self) -> None:
        """A structural guard, not a restatement of the test above.

        The seam breaks the day someone adds a `hash_paper_hex()` helper "just for
        convenience" — at which point a bare digest is loose again and the serializer
        can be handed one. This fails when that function is written, not later when
        something mislabels its output.
        """
        public_functions = {
            name
            for name, obj in vars(hashing).items()
            if not name.startswith("_")
            and inspect.isfunction(obj)
            and obj.__module__ == hashing.__name__
        }

        assert public_functions == {"hash_paper"}

    def test_the_algorithm_cannot_be_supplied_by_a_caller(self) -> None:
        """Mislabeling is unrepresentable, not merely rejected.

        `PaperHash("md5", ...)` must not be constructible at all. Validating a
        caller-supplied algorithm would leave the record with two sources of truth and
        the constant as the loser whenever they disagree.
        """
        with pytest.raises(TypeError):
            PaperHash("md5", digest_of(PAPER_LF))  # type: ignore[call-arg]

    def test_the_algorithm_cannot_be_reassigned(self) -> None:
        result = hash_paper(PAPER_LF)

        with pytest.raises(FrozenInstanceError):
            result.algorithm = "md5"  # type: ignore[misc]

    def test_the_digest_cannot_be_reassigned(self) -> None:
        result = hash_paper(PAPER_LF)

        with pytest.raises(FrozenInstanceError):
            result.digest = "deadbeef"  # type: ignore[misc]

    def test_nothing_can_be_attached_with_object_setattr(self) -> None:
        """`slots=True` is load-bearing: without it there is a `__dict__` to write to.

        `PaperHash` has no base class of its own, so nothing can re-open it the way an
        un-slotted base re-opens a union's variants (the trap `location.py` documents).
        """
        result = hash_paper(PAPER_LF)

        with pytest.raises(AttributeError):
            object.__setattr__(result, "truncated", True)

    def test_the_record_has_no_instance_dict(self) -> None:
        assert not hasattr(hash_paper(PAPER_LF), "__dict__")


class TestDigestValidation:
    """A record may not carry something that is not a digest of its own algorithm."""

    @pytest.mark.parametrize(
        "bad",
        [
            "",  # empty
            "deadbeef",  # too short
            digest_of(PAPER_LF) + "00",  # too long
            digest_of(PAPER_LF).upper(),  # not lowercase
            digest_of(PAPER_LF)[:-1] + "g",  # not hex
        ],
    )
    def test_a_malformed_digest_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            PaperHash(digest=bad)

    @pytest.mark.parametrize("bad", [None, 12, b"a" * 64])
    def test_a_non_string_digest_is_rejected(self, bad: object) -> None:
        with pytest.raises(TypeError):
            PaperHash(digest=bad)  # type: ignore[arg-type]


class TestDeterminism:
    """No ambient state: the same string is the same record, always."""

    def test_repeated_calls_agree(self) -> None:
        assert hash_paper(PAPER_LF) == hash_paper(PAPER_LF) == hash_paper(PAPER_LF)

    def test_distinct_papers_get_distinct_digests(self) -> None:
        assert digest_of(PAPER_LF) != digest_of(CAFE_NFC)

    def test_equal_records_compare_equal_across_construction_paths(self) -> None:
        # Phase 2 will key on this record; value equality has to hold however it was
        # built, not only when it came from the same call.
        assert hash_paper(PAPER_LF) == PaperHash(digest=digest_of(PAPER_LF))


class TestDomainSeparation:
    """A paper digest may not coincide with another record's digest over one input."""

    def test_differs_from_a_bare_sha256_of_the_normalized_text(self) -> None:
        bare = hashlib.sha256(normalize_text(PAPER_LF).encode("utf-8")).hexdigest()
        assert digest_of(PAPER_LF) != bare

    def test_differs_from_the_same_bytes_under_the_claim_id_scheme(self) -> None:
        # The concrete collision the prefix rules out: `claim.py` hashes under
        # b"plumb.claim.id.v1". Spelled out here rather than imported, so the test
        # fails if the paper scheme is ever changed to that value.
        payload = normalize_text(PAPER_LF).encode("utf-8")
        claim_scheme = hashlib.sha256(b"plumb.claim.id.v1")
        claim_scheme.update(payload)

        assert digest_of(PAPER_LF) != claim_scheme.hexdigest()


class TestInputContract:
    """`hash_paper` takes text. Not a path, not bytes."""

    @pytest.mark.parametrize(
        "bad",
        [
            b"We report AUC 0.87",
            None,
            12,
            ["We report AUC 0.87"],
        ],
    )
    def test_non_string_input_is_rejected(self, bad: object) -> None:
        # Bytes especially: accepting them would let a caller pass undecoded file
        # content and get a digest over text that was never normalized.
        with pytest.raises(TypeError):
            hash_paper(bad)  # type: ignore[arg-type]
