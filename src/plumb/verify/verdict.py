"""The Verdict record, and the set of them one run produced (M5, M6; D5).

**A decided verdict cannot exist without its evidence.** `REPRODUCED`,
`WITHIN-TOLERANCE` and `DIVERGED` are refused unless the record carries the text
the run wrote, the `Decimal` it became, the artifact it was bound to and that
artifact's SHA-256, the run it came from, the delta, and the band or threshold
that decided it — `WITHIN-TOLERANCE` additionally the tolerance. So no code path,
present or future, can emit a verdict that is not traceable to a fresh output of
a real run (`CLAUDE.md` #1, #5).

**`UNVERIFIED` names its cause; nothing else does.** The cause must be in the
closed vocabulary (`plumb.verify.causes.CAUSES`); the proposer's reserved causes
are refused because no proposer exists.

**`review_required` is derived:** it is true exactly for `DIVERGED`, the R2
human-in-the-loop hook — nothing in C4 publishes a finding.

**`bound`** means a value was located and parsed (the claim reached comparison),
whatever the verdict — the coverage number never hides an `UNVERIFIED` inside a
pass rate, and never counts a claim that bound to nothing as bound.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from plumb.verify.bindings import Locator
from plumb.verify.causes import CAUSES
from plumb.verify.compare import (
    DIVERGED,
    REPRODUCED,
    UNVERIFIED,
    VERDICTS,
    WITHIN_TOLERANCE,
)

__all__ = ["Verdict", "VerdictSet"]

Band = tuple[Decimal, Decimal]

_DECIMAL_FIELDS = ("rederived", "threshold", "tolerance_threshold", "delta")
_BAND_FIELDS = ("band", "tolerance_band")
_EVIDENCE = ("located_text", "sha256", "run_id", "rederived", "delta", "artifact", "locator")


@dataclass(frozen=True, slots=True)
class Verdict:
    """One claim's verdict, with everything that decided it."""

    claim_id: str
    verdict: str
    cause: str | None
    reported_text: str
    artifact: str | None  # the binding's target: a relpath or "<stdout>"
    locator: Locator | None
    located_text: str | None  # verbatim, as the run wrote it
    sha256: str | None  # the artifact's content address
    run_id: str | None  # None only when nothing ran
    rederived: Decimal | None  # located value × scale
    band: Band | None
    tolerance_band: Band | None
    threshold: Decimal | None
    tolerance_threshold: Decimal | None
    delta: Decimal | None

    def __post_init__(self) -> None:
        for name in _DECIMAL_FIELDS:
            _decimal(name, getattr(self, name))
        for name in _BAND_FIELDS:
            band = getattr(self, name)
            if band is not None:
                if not isinstance(band, tuple) or len(band) != 2:
                    raise TypeError(f"{name} must be a (low, high) pair")
                for end in band:
                    _decimal(name, end)
                    if end is None:
                        raise TypeError(f"{name} ends must be Decimals")

        if self.verdict not in VERDICTS:
            raise ValueError(f"unknown verdict {self.verdict!r}")
        if self.verdict == UNVERIFIED:
            if self.cause is None:
                raise ValueError(f"claim {self.claim_id}: UNVERIFIED must name its cause")
            if self.cause not in CAUSES:
                raise ValueError(
                    f"claim {self.claim_id}: cause {self.cause!r} is not in the vocabulary"
                )
            return

        if self.cause is not None:
            raise ValueError(f"claim {self.claim_id}: only UNVERIFIED carries a cause")
        for name in _EVIDENCE:
            if getattr(self, name) is None:
                raise ValueError(f"claim {self.claim_id}: {self.verdict} requires {name}")
        if self.band is None and self.threshold is None:
            raise ValueError(f"claim {self.claim_id}: {self.verdict} requires a band or threshold")
        if (
            self.verdict == WITHIN_TOLERANCE
            and self.tolerance_band is None
            and self.tolerance_threshold is None
        ):
            raise ValueError(f"claim {self.claim_id}: WITHIN-TOLERANCE requires its tolerance")

    @property
    def review_required(self) -> bool:
        return self.verdict == DIVERGED

    @property
    def bound(self) -> bool:
        return self.located_text is not None


@dataclass(frozen=True, slots=True)
class VerdictSet:
    """Every claim's verdict against one run, sorted by claim id, plus coverage."""

    run_id: str | None
    verdicts: tuple[Verdict, ...]

    def __post_init__(self) -> None:
        ids = [v.claim_id for v in self.verdicts]
        if ids != sorted(set(ids)):
            raise ValueError("verdicts must be unique and sorted by claim_id")

    @property
    def coverage(self) -> dict[str, Any]:
        """Counts derived from the records alone — never tracked on the side."""
        by_verdict = Counter(v.verdict for v in self.verdicts)
        return {
            "claims": len(self.verdicts),
            "bound": sum(v.bound for v in self.verdicts),
            "by_verdict": {
                name: by_verdict[name]
                for name in (REPRODUCED, WITHIN_TOLERANCE, DIVERGED, UNVERIFIED)
            },
            "by_cause": dict(sorted(Counter(v.cause for v in self.verdicts if v.cause).items())),
        }


def _decimal(name: str, value: Any) -> None:
    if value is not None and type(value) is not Decimal:
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
