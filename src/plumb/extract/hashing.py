"""The content hash that names a paper: sha256 over its **normalized** text.

Two decisions here carry beyond this file.

**The digest covers the normalized text, not the raw input.** `normalize_text` is the
single normal form every `CharSpan` offset is measured against (`location.py`), so
hashing the same bytes those offsets index keeps a published verdict anchored to the
exact content its own citations point at. Hashing the raw input instead would make the
same paper hash differently on a Windows checkout and a macOS one — two digests for one
paper, and a C6 replay that cannot match either.

**The algorithm is recorded, not implicit, and never travels apart from its digest.**
A third party replaying a verdict (C6) must read which function produced the digest
rather than guess it, and "obviously sha256" stops being obvious the day this is
bumped. So `hash_paper` returns a `PaperHash` carrying both, not a bare hex string.
The failure that shape rules out is specific: a digest arriving from somewhere else
and being stamped `"sha256"` by a downstream serializer would be *mislabeled*, which
is worse than unlabeled — a replayer is told how to verify it and the instruction is
wrong, so the check fails against content that was never wrong.

The algorithm is a constant, imported — never a parameter. Parameterizing it would add
a second input and turn "identical input → identical bytes" into "identical input *and
callers who agree* → identical bytes", which is not a contract.

This module emits no verdicts. It names content, nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib

from plumb.extract.location import normalize_text

__all__ = ["PAPER_HASH_ALGORITHM", "PaperHash", "hash_paper"]


#: The hash function `hash_paper` uses, named so it can be recorded alongside any
#: digest it produces. Changing this means changing every paper digest ever issued, so
#: it travels with the output rather than living only in this file.
PAPER_HASH_ALGORITHM = "sha256"

# Domain separation: a paper's digest must never coincide with some other record's
# digest over the same bytes. `claim.py` hashes claim ids under b"plumb.claim.id.v1";
# this is the analogous tag for papers. One variable-length field follows a
# fixed-length prefix, so the split is unambiguous without length-prefixing — the
# ambiguity `claim.py` length-prefixes against (`("ab","c")` vs `("a","bc")`) needs two
# fields to arise. A second field must not simply be appended; it would need the
# length-prefixed encoding and a bumped version tag.
_PAPER_SCHEME = b"plumb.paper.v1"

_HEX = frozenset("0123456789abcdef")


@dataclass(frozen=True, slots=True)
class PaperHash:
    """A paper's digest together with the algorithm that produced it.

    The two are one value because either alone is a trap: a digest without its
    algorithm cannot be verified, and an algorithm attached to a digest it did not
    produce is a wrong instruction to whoever tries.

    **`algorithm` is derived, never supplied.** It is `init=False` so that
    `PaperHash("md5", digest)` is not merely rejected but *unrepresentable* — there is
    one source of truth, `PAPER_HASH_ALGORITHM`, and a caller-supplied copy could only
    ever disagree with it. This follows `Claim.id`, which is derived for the same
    reason. (Reading a digest produced under a *past* algorithm is a different job:
    that is a versioned decode path belonging to whatever loads an archived C6 bundle,
    and it should be explicit rather than arriving through this constructor.)

    `digest` is checked to be lowercase hex of the exact length the named algorithm
    produces. Without that, any string at all could sit in this field wearing the
    algorithm's name — the mislabeling the record exists to prevent, one layer in.

    `slots=True` is load-bearing, not a micro-optimisation: it removes the `__dict__`
    that would otherwise let `object.__setattr__` attach a field (say, `truncated`)
    that every reader of this record would then miss.
    """

    digest: str
    algorithm: str = field(init=False, default=PAPER_HASH_ALGORITHM)

    def __post_init__(self) -> None:
        if not isinstance(self.digest, str):
            raise TypeError(
                "PaperHash.digest must be a hex string, got "
                f"{type(self.digest).__name__}: {self.digest!r}"
            )
        expected = hashlib.new(self.algorithm).digest_size * 2
        if len(self.digest) != expected:
            raise ValueError(
                f"PaperHash.digest must be {expected} hex characters for "
                f"{self.algorithm}, got {len(self.digest)}: {self.digest!r}"
            )
        if not _HEX.issuperset(self.digest):
            raise ValueError(
                "PaperHash.digest must be lowercase hex; uppercase or non-hex "
                f"characters would not compare equal to a digest we produced: "
                f"{self.digest!r}"
            )


def hash_paper(raw: str) -> PaperHash:
    """Return the `PaperHash` naming `raw`, taken over its normalized text.

    Takes the text itself, never a path: this function reads no file, no clock, and no
    environment, so the same string is the same digest in any process on any machine.
    Reading the paper is intake's job, and a digest that depended on where a file sat
    would not survive the trip to a replaying third party.

    `bytes` are rejected along with every other non-string input. Accepting them would
    let a caller hand over undecoded file content and receive a digest over text that
    was never normalized — the one failure this module exists to prevent, arriving
    silently.
    """
    if not isinstance(raw, str):
        raise TypeError(
            "hash_paper takes the paper's text, not a path or raw bytes; got "
            f"{type(raw).__name__}: {raw!r}"
        )
    digest = hashlib.new(PAPER_HASH_ALGORITHM, _PAPER_SCHEME)
    digest.update(normalize_text(raw).encode("utf-8"))
    return PaperHash(digest=digest.hexdigest())
