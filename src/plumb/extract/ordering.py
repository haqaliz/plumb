"""The ordering contract: one total key per record shape, for every module that sorts.

`dedup.py` and `serialize.py` both have to put the same records in the same order, and
for a while they did it by each holding its own copy of these functions, spelled
identically on purpose and guarded by tests asserting the two copies agreed. That guard
worked, but it could only ever fire *after* someone edited one copy. The functions live
here now, so there is nothing to keep in agreement.

**Every key here must be total.** A tie is a fallback to input order — `sorted()` is
stable, so two records that tie come back in the order they arrived, and arrival order
is exactly what both consumers exist to stop depending on. A partial key does not
announce itself: the suite stays green and the output is only nondeterministic for
inputs the fixtures happen not to contain.

**Nothing here reads ambient state.** No clock, no environment, no `hash()` — whose
seed varies per process, which a single-process test can never see.

These names are public within the package rather than underscore-prefixed. Two modules
import them; a leading underscore on a cross-module import would be describing the
opposite of what is true.
"""

from __future__ import annotations

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, Location

__all__ = [
    "ClaimIdentity",
    "identity_sort_key",
    "location_sort_key",
    "member_sort_key",
    "optional_sort_key",
]


ClaimIdentity = tuple[str, str, str | None]
"""`(reported_value.text, metric, units)` — the same fields `Claim.id` covers."""


def optional_sort_key(part: str | None) -> tuple[int, str]:
    """Order a `str | None` field without collapsing `None` into `""`.

    The obvious spelling — `part or ""` — makes `None` and `""` tie, and they are
    different facts the record layer went out of its way to keep apart ("this metric
    is dimensionless" versus "someone wrote an empty string"). `Claim.id` distinguishes
    them; a sort key that does not would hand two distinct claims an order decided by
    whoever appended them first.
    """
    return (0, "") if part is None else (1, part)


def location_sort_key(location: Location) -> tuple[str, int, int]:
    """Order locations by variant tag, then `(start, end)`.

    The tag leads so that a second variant joining the union orders against `CharSpan`
    rather than colliding with it. A `PageBox` given a `start` "for convenience" would
    otherwise sort page numbers against character offsets, and ordering would go
    silently meaningless while the suite stayed green. Until such a variant exists, an
    unknown one is refused: it has no offsets to sort on, and ordering it by arrival
    would reintroduce the dependence on extraction order both consumers exist to remove.

    **The tag is a deliberate seam, and today it discriminates nothing.** `CharSpan` is
    the only `Location` variant, so every key this function returns begins with
    `"char_span"` and replacing `location.kind` with that literal passes the whole
    suite. What the tests pin is the tag's *presence and position* — that the key is a
    3-tuple led by `CharSpan.kind` — not that it is read off the instance, and no test
    can pin the latter until a second variant exists to be read differently. Stated
    here rather than left for a reader to discover from a surviving mutant.

    It is kept anyway, because the protection that is real today is the refusal below:
    an unregistered variant raises instead of sorting. The tag is what makes it safe to
    *lift* that refusal when `PageBox` lands — at which point the alternative is a key
    whose first component is a page number in one record and a character offset in the
    next, comparing fine and meaning nothing.
    """
    if not isinstance(location, CharSpan):
        raise TypeError(
            f"{type(location).__name__} has no defined ordering; extend "
            "`location_sort_key` in plumb.extract.ordering when a Location variant "
            "joins the union, rather than letting output order fall back to "
            "extraction order."
        )
    return (location.kind, location.start, location.end)


def identity_sort_key(identity: ClaimIdentity) -> tuple[str, str, tuple[int, str]]:
    """Order groups by value text, then metric, then units."""
    text, metric, units = identity
    return (text, metric, optional_sort_key(units))


def member_sort_key(
    claim: Claim,
) -> tuple[tuple[str, int, int], tuple[int, str], tuple[int, str]]:
    """Order claims *within* one group — they already share text, metric and units.

    Location, then the two hints, which is every remaining field that may legitimately
    vary inside a group. Two members can tie here only if they are fully equal records
    (order unobservable) or if they disagree on `reported_value` components, which
    `dedup.py`'s `_require_coherent` has already refused.
    """
    return (
        location_sort_key(claim.location),
        optional_sort_key(claim.artifact_hint),
        optional_sort_key(claim.tolerance_hint),
    )
