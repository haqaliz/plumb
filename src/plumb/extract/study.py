"""`StudyParameter`: a number a paper reported *about the study*, not about its results.

The only inhabitant that matters today is the reported sample size, N.

**Why this type exists at all, and why it is not a `Claim`.** N has to be extracted:
C7, internal-consistency checking, verifies a paper's reported statistics against its
reported N, and depends on C1 for it. But N is not a claim, and it fails both of the
admission tests a claim must pass. It carries **no named metric** — "n" names a
population, not a measured quantity — and it is **not asserted about the paper's own
results**; it is study metadata, true of the experiment before any result exists.

The decisive reason is arithmetic rather than taxonomic. **No execution ever re-derives
a sample size.** Plumb's Phase 0 gate is a coverage number: the fraction of headline
claims that bind to an artifact and re-derive. Admitting N as a claim would drop a
permanently-unbindable item into that denominator, and the number would come out lower
for a reason that has nothing to do with how well Plumb works. A separate type is what
keeps that number honest, and it is why `StudyParameter` shares no base class with
`Claim` — a common ancestor, even an empty marker one, is how the distinction would
erode: a later stage would type against the base and start accepting N wherever it
meant claims.

**There is no `id`.** `Claim` derives one because aspect 3 requires claims reported in
several places to merge into a single record with a stable identity. No equivalent
requirement has been stated for study parameters. Whether two mentions of N merge, and
on what key — the name, the verbatim value, both — is a decision C7 is entitled to make
when it is built, and deriving a hash here would make it look as though that decision
had already been taken. The dataclass's own structural equality is the default, not an
identity scheme, and nothing downstream should read it as a dedup key.

**There is no `confidence`,** for exactly the guardrail reason `Claim` has none: a
confidence float becomes a model's opinion standing in for a re-derived value, and only
execution assigns verdicts (`CLAUDE.md` #1).

**Shape only.** Deciding which text becomes a `StudyParameter` is aspect 2's job; this
module holds no extraction or selection logic. It emits no verdicts.
"""

from __future__ import annotations

from dataclasses import dataclass

from plumb.extract.location import Location
from plumb.extract.value import ClaimValue

__all__ = ["StudyParameter"]


@dataclass(frozen=True, slots=True)
class StudyParameter:
    """One reported study parameter, pinned to where the paper stated it.

    Deliberately **not** a `Claim` and not substitutable for one — see the module
    docstring for why the coverage denominator depends on that.

    Every field must be stated at construction; none has a default, because none of
    the three is optional in any useful sense.

    Fields:

    - `name` — the parameter as the paper named it (`"n"`, `"sample size"`), required
      and non-empty. C7 asks for *the reported N* by name; a nameless record would
      force a later stage to re-read the prose to work out which parameter it holds,
      which is the guessing this project does not do.
    - `value` — the reported number in the shape the paper wrote it, carrying its
      verbatim text and its `Decimal`. The same `ClaimValue` union a claim uses: a
      reported N is still a reported number, and `1,024` must stay quotable as
      `1,024`. A bare `int` or `Decimal` here would have discarded the text before it
      arrived.
    - `location` — where in the normalized paper text the value was read from.
    """

    name: str
    value: ClaimValue
    location: Location

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError(
                f"StudyParameter.name must be a string, got "
                f"{type(self.name).__name__}: {self.name!r}"
            )
        if not self.name.strip():
            raise ValueError(
                "StudyParameter.name must name the parameter and may not be empty; "
                "an unnamed parameter cannot be looked up by the capability that "
                "needs it."
            )
        if not isinstance(self.value, ClaimValue):
            raise TypeError(
                "StudyParameter.value must be a ClaimValue variant, got "
                f"{type(self.value).__name__}: {self.value!r}"
            )
        if not isinstance(self.location, Location):
            raise TypeError(
                "StudyParameter.location must be a Location variant, got "
                f"{type(self.location).__name__}: {self.location!r}"
            )
