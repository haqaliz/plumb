"""The closed vocabulary of reasons a bundle does not verify.

These are facts about a **bundle**, not verdicts about a paper: a bundle that fails is simply
not evidence. None of them is ever turned into `DIVERGED` (or into any verdict at all).
"""

from __future__ import annotations

__all__ = [
    "BUNDLE_CAUSES",
    "CLAIMS_UNGROUNDED",
    "MANIFEST_INVALID",
    "MEMBER_MISSING",
    "MEMBER_REFUSED",
    "MEMBER_TAMPERED",
    "MEMBER_UNLISTED",
    "PAPER_MISMATCH",
    "PAPER_MISSING",
    "SIGNATURE_INVALID",
    "SIGNATURE_MISSING",
    "VERDICTS_MISMATCH",
    "BundleRefused",
]

#: No `manifest.sig` next to the manifest.
SIGNATURE_MISSING = "SIGNATURE_MISSING"
#: The signature is not the verifier's trusted principal's over these manifest bytes.
SIGNATURE_INVALID = "SIGNATURE_INVALID"
#: Not a readable plumb bundle: no manifest, a malformed field, a member that does not
#: parse, a trace that does not match the manifest, a bound object left out.
MANIFEST_INVALID = "MANIFEST_INVALID"
#: A member the manifest lists is absent.
MEMBER_MISSING = "MEMBER_MISSING"
#: A member's bytes do not match the hash or size the manifest lists.
MEMBER_TAMPERED = "MEMBER_TAMPERED"
#: A file in the bundle that the manifest does not list.
MEMBER_UNLISTED = "MEMBER_UNLISTED"
#: Content a bundle must never carry: a local path, a stderr stream, an output the run did
#: not produce, a symlink.
MEMBER_REFUSED = "MEMBER_REFUSED"
#: The paper is neither in the bundle nor supplied by the verifier; claims cannot be grounded.
PAPER_MISSING = "PAPER_MISSING"
#: The paper at hand is not the paper the bundle was built on.
PAPER_MISMATCH = "PAPER_MISMATCH"
#: A claim does not re-admit against the paper at its span.
CLAIMS_UNGROUNDED = "CLAIMS_UNGROUNDED"
#: The verdicts re-derived from the signed evidence differ from the signed verdicts.
VERDICTS_MISMATCH = "VERDICTS_MISMATCH"

BUNDLE_CAUSES = frozenset({
    SIGNATURE_MISSING, SIGNATURE_INVALID, MANIFEST_INVALID, MEMBER_MISSING, MEMBER_TAMPERED,
    MEMBER_UNLISTED, MEMBER_REFUSED, PAPER_MISSING, PAPER_MISMATCH, CLAIMS_UNGROUNDED,
    VERDICTS_MISMATCH,
})


class BundleRefused(ValueError):
    """`build_bundle` will not sign a bundle that would not verify."""

    def __init__(self, message: str, cause: str | None = None) -> None:
        super().__init__(message)
        self.cause = cause
