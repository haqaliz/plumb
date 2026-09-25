"""C4 binding & verdict: bind each claim to a value this run produced, and decide.

The public seam of the verify package — the first code in Plumb that emits a
verdict. `verify_claims(claims, bindings, run)` joins C1's `Claim` records and
C3's run: for each claim it locates exactly one value in a fresh, hash-checked
output of the run (`locate.py`), and decides it against the paper's reported
value (`compare.py`), yielding one evidence-carrying `Verdict` per claim
(`verdict.py`).

**Execution decides** (`CLAUDE.md` #1). Bindings are user-written in this slice
(`bindings.py`); no model proposes, and nothing here reads a claim's
`artifact_hint`. Every decided verdict carries the artifact's SHA-256 and the
run's id, and the record refuses one without them.

**Run causes govern, in this order** (first match wins):

1. `NoRun` — nothing ran (C3/C2 raised before any trace existed): every claim
   is `UNVERIFIED` with that cause;
2. the trace's recorded failure (`WONT_RUN`, `TIMEOUT`): every claim, even if the
   failed run's outputs were captured and would have matched;
3. `NO_ARTIFACT`: every claim;
4. per claim: no binding → `NO_BINDING`; then locate, then compare.

So **no harness-side failure can produce `DIVERGED`** (`CLAUDE.md` #3). The
precedence lives in `_run_level_cause`, which the guard test patches out to
prove the suite would notice.

**Cause vocabulary** — closed; every `UNVERIFIED` names one:

| Cause | Decided in | When |
|---|---|---|
| `ENTRYPOINT_MISSING`, `ENTRYPOINT_AMBIGUOUS` | seam (`NoRun`) | C3 found no entry point, or more than one |
| `ENV_BUILD_FAILED` | seam (`NoRun`) | C2's environment build failed; nothing ran |
| `WONT_RUN`, `TIMEOUT` | seam | the run failed or was killed |
| `NO_ARTIFACT` | seam | the run succeeded but wrote nothing capturable |
| `NO_BINDING` | seam / locate | no binding; target not written; locator matched nothing |
| `STALE_ARTIFACT` | locate | the target predates the run; its bytes are never read |
| `AMBIGUOUS_BINDING` | locate | the locator matched more than one value |
| `BINDING_INVALID` | locate | the binding entry's locator is unusable |
| `UNPARSEABLE_VALUE` | locate | the located text is not a plain number |
| `UNSUPPORTED_VALUE_KIND` | compare | `PlusMinus`, `Interval`, `Range`, `Approximate` |
| `UNIT_UNDECLARED` | compare | a percent claim whose binding declares no scale |
| `PRECISION_AMBIGUOUS` | compare | a round integer with no tolerance |
| `ARTIFACT_PRECISION_COARSER` | compare | the run wrote fewer digits, and agrees at its own precision |
| `NO_TOLERANCE` | compare | a relative tolerance of a reported zero |

**Not caught:** an integrity failure of the object store (`Capture.read`'s
`ValueError`), a `trace`/`capture` mismatch, or any unexpected exception. Those
are harness bugs, and a harness bug is never folded into a verdict.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from plumb.extract.claim import Claim
from plumb.intake.causes import EnvBuildFailed
from plumb.run.capture import Capture
from plumb.run.causes import EntryPointAmbiguous, EntryPointMissing
from plumb.run.trace import RunTrace, derive_run_id
from plumb.verify.bindings import Binding, load_bindings
from plumb.verify.causes import (
    CAUSES,
    ENTRYPOINT_AMBIGUOUS,
    ENTRYPOINT_MISSING,
    ENV_BUILD_FAILED,
    NO_ARTIFACT,
    NO_BINDING,
    BindingInvalid,
)
from plumb.verify.compare import (
    DIVERGED,
    REPRODUCED,
    UNVERIFIED,
    WITHIN_TOLERANCE,
    decide,
)
from plumb.verify.locate import Unlocated, locate
from plumb.verify.serialize import serialize_verdicts
from plumb.verify.verdict import Verdict, VerdictSet

__all__ = [
    "CAUSES",
    "DIVERGED",
    "REPRODUCED",
    "UNVERIFIED",
    "WITHIN_TOLERANCE",
    "BindingInvalid",
    "Completed",
    "NoRun",
    "Verdict",
    "VerdictSet",
    "load_bindings",
    "serialize_verdicts",
    "verify_claims",
]

_PRE_RUN = frozenset({ENTRYPOINT_MISSING, ENTRYPOINT_AMBIGUOUS, ENV_BUILD_FAILED})


@dataclass(frozen=True)
class Completed:
    """A run that happened: its trace, and the capture its outputs are read from."""

    trace: RunTrace
    capture: Capture


@dataclass(frozen=True)
class NoRun:
    """Nothing ran; `cause` says why."""

    cause: str

    def __post_init__(self) -> None:
        if self.cause not in _PRE_RUN:
            raise ValueError(f"{self.cause!r} is not a cause that stops a run before it starts")

    @classmethod
    def from_exception(cls, exc: BaseException) -> NoRun:
        """The `NoRun` for C3's entry-point errors or C2's `EnvBuildFailed`."""
        if isinstance(exc, (EntryPointMissing, EntryPointAmbiguous)):
            return cls(exc.cause)
        if isinstance(exc, EnvBuildFailed):
            return cls(ENV_BUILD_FAILED)
        raise TypeError(f"{type(exc).__name__} is not a named pre-run cause")


def verify_claims(
    claims: Iterable[Claim], bindings: Mapping[str, Binding], run: Completed | NoRun
) -> VerdictSet:
    """One verdict per claim against `run`, sorted by claim id."""
    ordered = sorted(claims, key=lambda c: c.id)
    ids = [c.id for c in ordered]
    if len(set(ids)) != len(ids):
        raise BindingInvalid("the claim set carries duplicate claim ids")
    orphans = set(bindings) - set(ids)
    if orphans:
        raise BindingInvalid(f"bindings name claims that were not given: {sorted(orphans)}")

    if isinstance(run, NoRun):
        return VerdictSet(None, tuple(_unverified(c, run.cause, None) for c in ordered))

    trace, capture = run.trace, run.capture
    if derive_run_id(trace.argv, trace.tree_hash, capture.artifacts) != trace.run_id:
        raise ValueError("the trace and the capture do not describe the same run")
    cause = _run_level_cause(trace)
    if cause is not None:
        return VerdictSet(trace.run_id, tuple(_unverified(c, cause, trace.run_id) for c in ordered))
    return VerdictSet(
        trace.run_id,
        tuple(_verify_one(c, bindings.get(c.id), capture, trace.run_id) for c in ordered),
    )


def _run_level_cause(trace: RunTrace) -> str | None:
    """The cause that governs every claim of this run, if the run itself failed."""
    if trace.failure is not None:
        return trace.failure.cause
    if NO_ARTIFACT in trace.causes:
        return NO_ARTIFACT
    return None


def _verify_one(
    claim: Claim, binding: Binding | None, capture: Capture, run_id: str
) -> Verdict:
    if binding is None:
        return _unverified(claim, NO_BINDING, run_id)
    found = locate(binding, capture)
    if isinstance(found, Unlocated):
        return _unverified(claim, found.cause, run_id, binding)

    decision = decide(
        claim.reported_value, claim.units, found.value, found.half_unit,
        binding.tolerance, binding.scale,
    )
    return Verdict(
        claim_id=claim.id,
        verdict=decision.verdict,
        cause=decision.cause,
        reported_text=claim.reported_value.text,
        artifact=binding.artifact,
        locator=binding.locator,
        located_text=found.text,
        sha256=found.sha256,
        run_id=run_id,
        rederived=decision.rederived,
        band=decision.band,
        tolerance_band=decision.tolerance_band,
        threshold=decision.threshold,
        tolerance_threshold=decision.tolerance_threshold,
        delta=decision.delta,
    )


def _unverified(
    claim: Claim, cause: str, run_id: str | None, binding: Binding | None = None
) -> Verdict:
    return Verdict(
        claim_id=claim.id,
        verdict=UNVERIFIED,
        cause=cause,
        reported_text=claim.reported_value.text,
        artifact=None if binding is None else binding.artifact,
        locator=None if binding is None else binding.locator,
        located_text=None,
        sha256=None,
        run_id=run_id,
        rederived=None,
        band=None,
        tolerance_band=None,
        threshold=None,
        tolerance_threshold=None,
        delta=None,
    )
