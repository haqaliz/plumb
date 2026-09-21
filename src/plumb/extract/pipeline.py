"""The deterministic spine end to end: paper text -> claims and their rejections.

This is the seam C4 and `plumb verify` consume: `extract_candidates` finds every
number, `selection.select` decides which are worth a claim, and `admit` — the sole
constructor of a `Claim` — grounds the survivors. Nothing here emits a verdict,
and nothing here can construct a `Claim` by another route: the gate remains the
only door (test_admit.py, AST-guarded).

`extract_claims` deliberately does not duplicate `study_parameters` (admit.py):
reported N leaves the pipeline through that separate record type, and the rule's
named-metric test keeps sample sizes out of the claim set (M11).
"""

from __future__ import annotations

from plumb.extract.admit import NON_CLAIM_CAUSES, NonClaim, admit
from plumb.extract.candidates import extract_candidates
from plumb.extract.claim import Claim
from plumb.extract.location import normalize_text
from plumb.extract.selection import Selected, SelectionRejection, select

__all__ = [
    "extract_claims",
]

Rejection = NonClaim | SelectionRejection


def extract_claims(
    raw: str,
) -> tuple[tuple[Claim, ...], tuple[Rejection, ...]]:
    """Every claim a paper makes, plus every number it does not.

    The paper is normalized once — the same bytes every span indexes — and the
    candidates, the rule, and the gate all read that one string. The gate's
    rejections and the rule's rejections come back in one sequence, each carrying
    its own closed cause vocabulary; C5 will want to tell a grounding miss from a
    worth miss apart.
    """
    normalized = normalize_text(raw)
    claims: list[Claim] = []
    rejections: list[Rejection] = []

    for candidate in extract_candidates(normalized):
        outcome = select(candidate, normalized_text=normalized)
        if isinstance(outcome, SelectionRejection):
            rejections.append(outcome)
            continue
        assert isinstance(outcome, Selected)
        admitted = admit(
            outcome.candidate,
            normalized_text=normalized,
            metric=outcome.metric,
            units=outcome.units,
        )
        if isinstance(admitted, NonClaim):
            rejections.append(admitted)
        else:
            claims.append(admitted)

    return tuple(claims), tuple(rejections)