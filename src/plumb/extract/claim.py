"""`Claim`: one quantitative assertion a paper made, as a record later stages consume.

A claim is *what the paper said*, pinned to *where it said it*, with enough of a hint
to go looking for the same quantity in the artifacts. It is deliberately inert: it
holds no judgement about whether the claim holds, because that judgement belongs to
execution alone (`CLAUDE.md` #1). This module emits no verdicts.

Two design decisions carry weight far beyond this file.

**The `id` excludes `location`** (decision D2 of the aspect plan). Aspect 3 merges a
claim reported in several places — an abstract, a results table, a figure caption —
into one record with several locations, and requires the id to come through that merge
unchanged. An id derived from location would make deduplication change identity, while
identity is the very thing deduplication is keyed on. So the id covers
`(reported_value.text, metric, units)` and nothing else.

**The id is derived from the verbatim `text`, never from the `Decimal`.**
`Decimal("0.870") == Decimal("0.87")` is `True` — `Decimal` compares numerically, not
representationally — so an id built on the parsed number would quietly fuse two values
the paper reported at different precisions, which is exactly the boundary case that
must stay two claims.

**There is no `confidence` field.** See `Claim`'s docstring; its absence is enforced by
a test, on purpose.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from plumb.extract.location import Location
from plumb.extract.value import ClaimValue

__all__ = ["Claim"]


# Domain separation: the digest of a claim should never coincide with the digest of
# some other record type that happens to hash the same three strings. Aspect 3 owns
# recording this algorithm and proving it stable across processes; if it pins a
# different scheme, this constant is the thing it bumps.
_ID_SCHEME = b"plumb.claim.id.v1"


def _encoded(part: str | None) -> bytes:
    """One field, encoded so no two different field tuples can produce one byte string.

    Concatenating fields is not enough: `("ab", "c")` and `("a", "bc")` both flatten to
    `abc`, and two different claims would share an id. A separator alone is not enough
    either, since any byte chosen as the separator can occur inside a field. So each
    field is length-prefixed — unambiguous whatever it contains — and tagged as present
    or absent, so that `None` (a dimensionless metric) and `""` (a caller who wrote an
    empty string) stay distinct.
    """
    if part is None:
        return b"\x00:"
    payload = part.encode("utf-8")
    return b"\x01:" + str(len(payload)).encode("ascii") + b":" + payload


def _derive_id(reported_value_text: str, metric: str, units: str | None) -> str:
    """SHA-256 over the identifying fields, in a pinned order.

    The order is part of the contract, not an implementation detail: reordering these
    three lines changes every id ever issued.
    """
    digest = hashlib.sha256(_ID_SCHEME)
    for part in (reported_value_text, metric, units):
        digest.update(_encoded(part))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class Claim:
    """A quantitative claim read out of a paper.

    Every field must be stated at construction — including the nullable ones. `None`
    is a thing the caller said, not a thing they got by leaving an argument out:
    "this metric is dimensionless" and "nobody looked for a unit" are different facts
    and a default would record them identically.

    **There is no `confidence` field, and this is a guardrail rather than an
    omission.** A confidence float on this record becomes `if claim.confidence > 0.9`
    at verdict time, which is a model's opinion standing in for a re-derived value —
    the substitution `CLAUDE.md` #1 and `docs/technical/ARCHITECTURE.md:8-10` exist to
    prevent. A model may propose a claim or a binding; only re-execution against the
    real run may assign a verdict. It is also unnecessary: a claim we are unsure of is
    not a low-confidence claim, it is a claim whose outcome is decided by running the
    artifact, and a claim that cannot be bound or run resolves to `UNVERIFIED` with a
    named cause — a fact about the run, not a number on the record. An extractor that
    wants to record how sure it was should keep that in its own output, where the
    verdict layer will not read it.

    Fields:

    - `reported_value` — the paper's number, in the shape the paper wrote it
      (`Point`, `Bound`, `Interval`, ...). Never flattened to a scalar.
    - `units` — the unit as the paper gave it, or `None` for a dimensionless metric
      such as an AUC or an F1. Whether `%` and percentage points are the same unit is
      an open question this record does not settle; it stores what was written.
    - `metric` — the named quantity, required and non-empty. C4 binds a claim by
      aiming a locator at a *named* quantity; with no name, a later stage would have
      to re-interpret the surrounding prose, which is the guessing this project does
      not do.
    - `location` — where in the normalized paper text the value was read from.
    - `artifact_hint` — where in the repo the same quantity might be re-derived, or
      `None`. A hint for a later stage to try, never an assertion that it is right.
    - `tolerance_hint` — the paper's own words about acceptable agreement, verbatim
      and unparsed, or `None`. A carrier only: what a tolerance *means* is an open
      design question owned elsewhere, and a parsed numeric tolerance sitting here
      would quietly settle it.
    - `id` — derived, never supplied. See the module docstring for D2.
    """

    reported_value: ClaimValue
    units: str | None
    metric: str
    location: Location
    artifact_hint: str | None
    tolerance_hint: str | None
    id: str = field(init=False, default="")

    def __post_init__(self) -> None:
        if not isinstance(self.reported_value, ClaimValue):
            raise TypeError(
                "Claim.reported_value must be a ClaimValue variant, got "
                f"{type(self.reported_value).__name__}: {self.reported_value!r}"
            )
        if not isinstance(self.location, Location):
            raise TypeError(
                "Claim.location must be a Location variant, got "
                f"{type(self.location).__name__}: {self.location!r}"
            )
        if not isinstance(self.metric, str):
            raise TypeError(
                f"Claim.metric must be a string, got {type(self.metric).__name__}: "
                f"{self.metric!r}"
            )
        if not self.metric.strip():
            raise ValueError(
                "Claim.metric must name the quantity and may not be empty; a claim "
                "with no named metric cannot be aimed at an artifact."
            )
        for name in ("units", "artifact_hint", "tolerance_hint"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(
                    f"Claim.{name} must be a string or None, got "
                    f"{type(value).__name__}: {value!r}"
                )

        object.__setattr__(
            self,
            "id",
            _derive_id(self.reported_value.text, self.metric, self.units),
        )
