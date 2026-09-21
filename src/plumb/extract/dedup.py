"""Value-identity dedup: recognising that two mentions are the same result.

A paper reports one number in several places — an abstract, a results table, a figure
caption. Those are one claim with three locations, not three claims, and counting them
three times would inflate every downstream tally. Recognising them is this module's
only job. It emits no verdicts (`CLAUDE.md` #1).

**The rule, in one sentence, because a third party must be able to reimplement it:**
two claims are the same claim when their `reported_value.text`, `metric` and `units`
are identical strings. Nothing is normalized, folded, rounded or canonicalized first.

That sentence is the whole contract, and it is deliberately the same three fields
`Claim.id` is derived from, so `claim_identity(a) == claim_identity(b)` and
`a.id == b.id` agree exactly rather than approximately. `Claim.id` excludes `location`
by design (`claim.py`'s D2), which is what makes merging locations safe: the merge
cannot change the identity it is keyed on.

**Numeric canonicalization is forbidden here, and the prohibition is the point.**
`Decimal("0.870") == Decimal("0.87")` is `True` — `Decimal` compares numerically, not
representationally — so keying identity on the parsed number would fuse two values the
paper stated at different precisions. Significant figures are semantic: a paper that
wrote `0.870` claimed three of them. Fusing that pair seeds a false `DIVERGED`
upstream, in the deduplicator, long before anything is compared (risk R2,
`docs/ROADMAP.md:57`). For the same reason `.87` and `0.87` stay two claims: pure
string identity is reimplementable from one sentence, and any normalization would have
to be documented, versioned, and replayable by C6.

**Ordering is by an explicit total key, never by insertion, `set` iteration or
`hash()`.** `PYTHONHASHSEED` varies from process to process, so any of those three
would make output order depend on which interpreter happened to run — and a single
-process test would never see it.

**A merged result is its own type, `MergedClaim`, sharing no base with `Claim`.** A
`Claim` is a *mention*: one value, one place. A `MergedClaim` is a *result*: one value,
N places. Growing `Claim` a `locations` tuple instead would have given that distinction
away — the singular `location` field is what makes "a claim is one mention" enforceable
for free, and an extractor handed a tuple could emit three locations that never went
through dedup. The two records also keep deliberately different field *names*
(`location` against `locations`), so consuming code that reaches for `claim.location`
without an `isinstance` check fails loudly on a merged record rather than silently
reading the first of several places the paper made the claim.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, Location
from plumb.extract.value import ClaimValue

__all__ = [
    "MergedClaim",
    "claim_identity",
    "dedup_claims",
    "group_claims",
    "merged_locations",
]


ClaimIdentity = tuple[str, str, str | None]
"""`(reported_value.text, metric, units)` — the same fields `Claim.id` covers."""


def claim_identity(claim: Claim) -> ClaimIdentity:
    """The identity two mentions must share to be one claim.

    Returned as the verbatim field values rather than as `claim.id`, so a reader can
    see what identity *is* instead of trusting a digest, and so a mismatch is legible
    in a failure message. The two agree by construction; `test_dedup.py` asserts it
    both ways.
    """
    _require_claim(claim)
    return (claim.reported_value.text, claim.metric, claim.units)


def group_claims(claims: Iterable[Claim]) -> tuple[tuple[Claim, ...], ...]:
    """Partition `claims` into one group per distinct identity.

    Groups come back in a defined order, and so do the members inside each group, on
    an explicit total key (see `_identity_sort_key` and `_member_sort_key`). Feeding
    the same claims in a different order returns exactly the same structure.

    Raises `ValueError` when two claims share an identity but carry non-equal
    `reported_value` records — see `_require_coherent`.
    """
    grouped: dict[ClaimIdentity, list[Claim]] = {}
    for claim in claims:
        grouped.setdefault(claim_identity(claim), []).append(claim)

    ordered: list[tuple[Claim, ...]] = []
    # `.items()` is insertion-ordered, which is deterministic only if the *input* was.
    # The sort is what makes the output order independent of the caller.
    for identity, members in sorted(
        grouped.items(), key=lambda item: _identity_sort_key(item[0])
    ):
        _require_coherent(identity, members)
        ordered.append(tuple(sorted(members, key=_member_sort_key)))
    return tuple(ordered)


def merged_locations(claims: Iterable[Claim]) -> tuple[Location, ...]:
    """Every distinct place these claims were read from, sorted by `(start, end)`.

    Duplicates collapse: the same claim extracted twice from the same span is one
    mention, and a merged record listing that span twice would assert the paper said
    it twice.

    Sort-then-collapse rather than a `set`, deliberately. A set would give the right
    *members* and an ordering that depends on `PYTHONHASHSEED`; sorting first makes
    the collapse a comparison between neighbours and leaves nothing to hash order.
    """
    ordered = sorted(
        (claim.location for claim in claims), key=_location_sort_key
    )
    unique: list[Location] = []
    for location in ordered:
        if not unique or unique[-1] != location:
            unique.append(location)
    return tuple(unique)


@dataclass(frozen=True, slots=True)
class MergedClaim:
    """One result, and every place the paper reported it.

    Not a `Claim` and not substitutable for one — see the module docstring. Frozen and
    slotted, like every record in this layer, so nothing can bolt a `confidence` field
    on afterwards (`CLAUDE.md` #1). Every field must be stated at construction.

    Fields:

    - `id` — **carried verbatim from the group, never re-derived here.** `Claim.id`
      excludes `location` by design, so every member of a group already shares one id
      and there is nothing to recompute. Re-deriving it would put a second copy of the
      hashing rule in a second module, where it could drift from the first.
    - `reported_value`, `units`, `metric` — the identity the group shares, unchanged.
      Exactly the three fields `id` covers.
    - `locations` — every distinct place the claim was read from, sorted. Never empty:
      a result nobody located is not a result.
    - `artifact_hints`, `tolerance_hints` — the distinct hints the merged mentions
      carried, sorted, with absent ones dropped rather than recorded as `None`. Plural
      because a hint is explicitly non-authoritative and the same result cited in an
      abstract (no hint) and in a results table (a hint) is the *normal* case, not an
      edge case. Keeping one and discarding the other would be silent information loss
      in the field C4 uses to go looking.

    The sorted-and-distinct invariants on all three collections are enforced at
    construction, not just produced by `dedup_claims`. A hand-built record with
    out-of-order locations would serialize differently from the identical record built
    here, which is precisely the input-order dependence this aspect exists to remove.
    """

    id: str
    reported_value: ClaimValue
    units: str | None
    metric: str
    locations: tuple[Location, ...]
    artifact_hints: tuple[str, ...]
    tolerance_hints: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError(
                f"MergedClaim.id must be a string carried from the group, got "
                f"{type(self.id).__name__}: {self.id!r}"
            )
        if not self.id:
            raise ValueError(
                "MergedClaim.id must be the id the group's claims share; an empty id "
                "would make two different results compare as one."
            )
        if not isinstance(self.reported_value, ClaimValue):
            raise TypeError(
                "MergedClaim.reported_value must be a ClaimValue variant, got "
                f"{type(self.reported_value).__name__}: {self.reported_value!r}"
            )
        if not isinstance(self.metric, str):
            raise TypeError(
                f"MergedClaim.metric must be a string, got "
                f"{type(self.metric).__name__}: {self.metric!r}"
            )
        if not self.metric.strip():
            raise ValueError(
                "MergedClaim.metric must name the quantity and may not be empty."
            )
        if self.units is not None and not isinstance(self.units, str):
            raise TypeError(
                f"MergedClaim.units must be a string or None, got "
                f"{type(self.units).__name__}: {self.units!r}"
            )

        # `tuple` specifically, not "any sequence": a list would be mutable and
        # unhashable, which unseals a record the rest of the layer treats as frozen.
        # A bare `str` would also pass an iterability check and then iterate per
        # character, which is the quiet version of the same mistake.
        if not isinstance(self.locations, tuple):
            raise TypeError(
                f"MergedClaim.locations must be a tuple, got "
                f"{type(self.locations).__name__}: {self.locations!r}"
            )
        if not self.locations:
            raise ValueError(
                "MergedClaim.locations must not be empty; a result with nowhere to "
                "quote it from cannot be checked against the paper."
            )
        for location in self.locations:
            if not isinstance(location, Location):
                raise TypeError(
                    "MergedClaim.locations must hold Location variants, got "
                    f"{type(location).__name__}: {location!r}"
                )
        _require_sorted_distinct("locations", self.locations, _location_sort_key)

        for name in ("artifact_hints", "tolerance_hints"):
            hints = getattr(self, name)
            if not isinstance(hints, tuple):
                raise TypeError(
                    f"MergedClaim.{name} must be a tuple, got "
                    f"{type(hints).__name__}: {hints!r}"
                )
            for hint in hints:
                if not isinstance(hint, str):
                    raise TypeError(
                        f"MergedClaim.{name} must hold strings — an absent hint is "
                        f"dropped, never recorded as None — got "
                        f"{type(hint).__name__}: {hint!r}"
                    )
            _require_sorted_distinct(name, hints, lambda hint: hint)


def dedup_claims(claims: Iterable[Claim]) -> tuple[MergedClaim, ...]:
    """Merge duplicate mentions into one `MergedClaim` per distinct identity.

    "Same id ⇒ merged, different id ⇒ not merged" holds exactly: the grouping key is
    the same three fields the id is derived from. Output order is the group order of
    `group_claims`, which is independent of input order.
    """
    return tuple(_merge_group(group) for group in group_claims(claims))


def _merge_group(group: Sequence[Claim]) -> MergedClaim:
    """Fold one already-validated group into a single record.

    The identity fields are taken from the first member rather than recomputed: every
    member shares them by definition of the group, and `_require_coherent` has already
    refused the one case where they could disagree.
    """
    first = group[0]
    return MergedClaim(
        id=first.id,
        reported_value=first.reported_value,
        units=first.units,
        metric=first.metric,
        locations=merged_locations(group),
        artifact_hints=_merged_hints(group, "artifact_hint"),
        tolerance_hints=_merged_hints(group, "tolerance_hint"),
    )


def _merged_hints(group: Sequence[Claim], attribute: str) -> tuple[str, ...]:
    """The distinct hints the group carried, sorted, with `None`s dropped.

    `None` means nobody proposed a hint, which an empty tuple says once rather than
    once per mention.

    Sort-then-collapse rather than `sorted(set(...))`, matching `merged_locations`.
    Both spellings are deterministic, but this one never builds a hash-ordered
    intermediate at all, so determinism is visible in the code instead of resting on
    the `sorted()` that follows.
    """
    ordered = sorted(
        getattr(claim, attribute)
        for claim in group
        if getattr(claim, attribute) is not None
    )
    unique: list[str] = []
    for hint in ordered:
        if not unique or unique[-1] != hint:
            unique.append(hint)
    return tuple(unique)


# --------------------------------------------------------------------------------
# Sort keys. Every one of these must be *total*: a tie is a fallback to input order,
# and input order is exactly what this module refuses to depend on.
# --------------------------------------------------------------------------------


def _optional_sort_key(part: str | None) -> tuple[int, str]:
    """Order a `str | None` field without collapsing `None` into `""`.

    The obvious spelling — `part or ""` — makes `None` and `""` tie, and they are
    different facts the record layer went out of its way to keep apart ("this metric
    is dimensionless" versus "someone wrote an empty string"). `Claim.id`
    distinguishes them; a sort key that does not would hand two distinct claims an
    order decided by whoever appended them first.
    """
    return (0, "") if part is None else (1, part)


def _identity_sort_key(identity: ClaimIdentity) -> tuple[str, str, tuple[int, str]]:
    """Order groups by value text, then metric, then units."""
    text, metric, units = identity
    return (text, metric, _optional_sort_key(units))


def _location_sort_key(location: Location) -> tuple[str, int, int]:
    """Order locations by variant tag, then `(start, end)`.

    The tag leads so that a second variant joining the union orders against `CharSpan`
    rather than colliding with it. Until one exists, an unknown variant is refused: it
    has no offsets to sort on, and ordering it by arrival would reintroduce the
    dependence on extraction order that this module exists to remove.
    """
    if not isinstance(location, CharSpan):
        raise TypeError(
            f"{type(location).__name__} has no defined ordering; extend "
            "`_location_sort_key` when a Location variant joins the union, rather "
            "than letting output order fall back to extraction order."
        )
    return (location.kind, location.start, location.end)


def _member_sort_key(
    claim: Claim,
) -> tuple[tuple[str, int, int], tuple[int, str], tuple[int, str]]:
    """Order claims *within* one group — they already share text, metric and units.

    Location, then the two hints, which is every remaining field that may legitimately
    vary inside a group. Two members can tie here only if they are fully equal records
    (order unobservable) or if they disagree on `reported_value` components, which
    `_require_coherent` has already refused.
    """
    return (
        _location_sort_key(claim.location),
        _optional_sort_key(claim.artifact_hint),
        _optional_sort_key(claim.tolerance_hint),
    )


# --------------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------------


def _require_sorted_distinct(
    field: str, items: Sequence[object], key: Callable[[object], object]
) -> None:
    """Refuse a collection that is out of order or repeats itself.

    Checked on adjacent pairs of the collection as given, which is what makes this a
    validation rather than a silent repair: sorting the caller's tuple for them would
    hide that they built it in an order determinism does not allow.
    """
    keyed = [key(item) for item in items]
    for earlier, later in zip(keyed, keyed[1:]):
        if earlier == later:
            raise ValueError(
                f"MergedClaim.{field} must be distinct; {later!r} appears twice. The "
                "same mention recorded twice would claim the paper said it twice."
            )
        if earlier > later:  # type: ignore[operator]  # total per `key`
            raise ValueError(
                f"MergedClaim.{field} must be sorted; {earlier!r} precedes {later!r}. "
                "An unsorted collection makes the record depend on the order its "
                "mentions happened to arrive in."
            )


def _require_claim(claim: object) -> None:
    if not isinstance(claim, Claim):
        raise TypeError(
            f"dedup operates on Claim records, got {type(claim).__name__}: {claim!r}"
        )


def _require_coherent(identity: ClaimIdentity, members: Sequence[Claim]) -> None:
    """Refuse a group whose members disagree about the value they share an id with.

    Identity is keyed on the verbatim `text`, so two claims can share an id while
    carrying different parsed numbers — `Point("0.87", Decimal("0.87"))` against
    `Point("0.87", Decimal("99"))`. `parse_value` is a function of the text and cannot
    produce that, so reaching it means a hand-built value is wrong upstream.

    Merging anyway would mean keeping one parse and discarding the other on a sort
    order the caller never saw — a silent pass over a real inconsistency, which
    `CLAUDE.md` #3 rules out. It fails loudly at the point of the mistake instead.
    """
    first = members[0].reported_value
    for other in members[1:]:
        if other.reported_value != first:
            raise ValueError(
                f"claims sharing the identity {identity!r} carry different "
                f"reported_value records ({first!r} and {other.reported_value!r}); "
                "identity is keyed on the verbatim text, so this is an inconsistent "
                "parse upstream, not a duplicate to merge."
            )
