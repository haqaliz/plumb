"""C7: internal-consistency checks for papers with no runnable artifact.

The weakest signal Plumb emits, and the only one that needs no code: do the numbers a paper
reports agree with each other? Two checks live here.

- `statcheck` — an explicitly reported test statistic and its df recompute a p; if the paper's
  own p disagrees at its own written precision, the paper is internally inconsistent. Compared
  against both the two-sided and one-sided p for `t`/`z`/`r`, so a one-sided report is never
  flagged.
- `GRIM` — a mean of integer-valued items over `N` must be reachable at its written precision.

**These are never verdicts.** No label here is `DIVERGED`, `REPRODUCED` or `UNVERIFIED`: an
internal inconsistency is not a re-execution of the paper's artifact, and this module has no
access to a run. The labels are `INTERNAL_INCONSISTENCY`, `CONSISTENT` and `NOT_APPLICABLE`, and
`CONSISTENT` means only "this check found nothing" — GRIM's applicability to a given mean
(integer-valued items) cannot be established from prose.
"""

from __future__ import annotations

from dataclasses import dataclass

from plumb.consistency.grim import scan_means
from plumb.consistency.statcheck import scan_statistics
from plumb.extract.location import CharSpan, normalize_text

__all__ = [
    "CONSISTENT",
    "ConsistencyReport",
    "Finding",
    "INTERNAL_INCONSISTENCY",
    "NOT_APPLICABLE",
    "check_consistency",
]

#: The paper's own numbers disagree; a weaker signal than an execution-grounded `DIVERGED`.
INTERNAL_INCONSISTENCY = "INTERNAL_INCONSISTENCY"
#: The check found nothing. Not a clean bill: the check may not apply.
CONSISTENT = "CONSISTENT"
#: The check does not apply (no df, no N, an unreadable value).
NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class Finding:
    """One checked passage, with the label the check gave it."""

    kind: str  # "statcheck" | "grim"
    label: str
    span: CharSpan
    reported: str
    detail: str


@dataclass(frozen=True)
class ConsistencyReport:
    """Every finding, in text order; counts derived from the records, never dropped."""

    findings: tuple[Finding, ...]

    @property
    def inconsistent(self) -> bool:
        return any(f.label == INTERNAL_INCONSISTENCY for f in self.findings)

    def counts(self) -> dict[str, int]:
        counts = {INTERNAL_INCONSISTENCY: 0, CONSISTENT: 0, NOT_APPLICABLE: 0}
        for finding in self.findings:
            counts[finding.label] += 1
        return counts


def check_consistency(raw: str) -> ConsistencyReport:
    """Check `raw` paper text; one finding per checked passage, sorted by position."""
    text = normalize_text(raw)
    findings = [
        Finding("statcheck", stat.label, stat.span, stat.reported, stat.detail)
        for stat in scan_statistics(text)
    ]
    findings += [
        Finding("grim", mean.label, mean.span, mean.reported, mean.detail)
        for mean in scan_means(text)
    ]
    return ConsistencyReport(tuple(sorted(findings, key=lambda f: (f.span.start, f.kind))))
