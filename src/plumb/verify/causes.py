"""The closed cause vocabulary of C4, and the one error a bindings file can raise.

Every `UNVERIFIED` verdict names exactly one cause from `CAUSES`; a verdict record
refuses any other (`CLAUDE.md` #3 — any failure to evaluate is named, never a
silent pass and never `DIVERGED`). The vocabulary is the union of:

- **Run-side causes** C2/C3 already produce. `WONT_RUN`, `TIMEOUT`,
  `NO_ARTIFACT` and `STALE_ARTIFACT` are the run package's own strings;
  `ENTRYPOINT_MISSING` / `ENTRYPOINT_AMBIGUOUS` are the `cause` of C3's raised
  exceptions; `ENV_BUILD_FAILED` names C2's `EnvBuildFailed`, which carries no
  cause attribute of its own.
- **Binding-side causes** — the claim could not be tied to exactly one parsed
  value of this run: `NO_BINDING`, `AMBIGUOUS_BINDING`, `BINDING_INVALID`,
  `UNPARSEABLE_VALUE`.
- **Comparison-side causes** — a value was located but the claim cannot be
  decided against it: `NO_TOLERANCE`, `UNSUPPORTED_VALUE_KIND`,
  `UNIT_UNDECLARED`, `PRECISION_AMBIGUOUS`, `ARTIFACT_PRECISION_COARSER`.

`PROPOSER_UNGROUNDED` and `MODEL_ONLY_SIGNAL` (`ARCHITECTURE.md`) are
**reserved**: they belong to a binding proposer that does not exist, so nothing
emits them and they are deliberately outside `CAUSES`.
"""

from __future__ import annotations

from plumb.run.causes import (
    NO_ARTIFACT,
    STALE_ARTIFACT,
    TIMEOUT,
    WONT_RUN,
    EntryPointAmbiguous,
    EntryPointMissing,
)

__all__ = [
    "AMBIGUOUS_BINDING",
    "ARTIFACT_PRECISION_COARSER",
    "BINDING_INVALID",
    "CAUSES",
    "ENTRYPOINT_AMBIGUOUS",
    "ENTRYPOINT_MISSING",
    "ENV_BUILD_FAILED",
    "NO_ARTIFACT",
    "NO_BINDING",
    "NO_TOLERANCE",
    "PRECISION_AMBIGUOUS",
    "RESERVED",
    "STALE_ARTIFACT",
    "TIMEOUT",
    "UNIT_UNDECLARED",
    "UNPARSEABLE_VALUE",
    "UNSUPPORTED_VALUE_KIND",
    "WONT_RUN",
    "BindingInvalid",
]

ENTRYPOINT_MISSING = EntryPointMissing.cause
ENTRYPOINT_AMBIGUOUS = EntryPointAmbiguous.cause
#: C2's `EnvBuildFailed`: the environment could not be built, so nothing ran.
ENV_BUILD_FAILED = "ENV_BUILD_FAILED"

#: No binding for the claim, or the locator found nothing in the run's outputs.
NO_BINDING = "NO_BINDING"
#: The locator matched more than one value; Plumb does not pick one.
AMBIGUOUS_BINDING = "AMBIGUOUS_BINDING"
#: The binding entry itself is unusable (bad pointer, regex, or CSV selector).
BINDING_INVALID = "BINDING_INVALID"
#: The located text is not a plain number.
UNPARSEABLE_VALUE = "UNPARSEABLE_VALUE"

#: No defensible tolerance: none given and none readable from the claim.
NO_TOLERANCE = "NO_TOLERANCE"
#: A value kind this slice does not compare (`PlusMinus`, `Interval`, ...).
UNSUPPORTED_VALUE_KIND = "UNSUPPORTED_VALUE_KIND"
#: A percent claim whose binding does not declare the artifact's scale.
UNIT_UNDECLARED = "UNIT_UNDECLARED"
#: A round integer (`10,000`) whose written precision cannot be read.
PRECISION_AMBIGUOUS = "PRECISION_AMBIGUOUS"
#: The artifact wrote fewer digits than the paper, and agrees at its own precision.
ARTIFACT_PRECISION_COARSER = "ARTIFACT_PRECISION_COARSER"

CAUSES = frozenset(
    {
        WONT_RUN,
        TIMEOUT,
        NO_ARTIFACT,
        STALE_ARTIFACT,
        ENTRYPOINT_MISSING,
        ENTRYPOINT_AMBIGUOUS,
        ENV_BUILD_FAILED,
        NO_BINDING,
        AMBIGUOUS_BINDING,
        BINDING_INVALID,
        UNPARSEABLE_VALUE,
        NO_TOLERANCE,
        UNSUPPORTED_VALUE_KIND,
        UNIT_UNDECLARED,
        PRECISION_AMBIGUOUS,
        ARTIFACT_PRECISION_COARSER,
    }
)

RESERVED = frozenset({"PROPOSER_UNGROUNDED", "MODEL_ONLY_SIGNAL"})


class BindingInvalid(ValueError):
    """The bindings file as a whole cannot be trusted; nothing is verified against it."""
