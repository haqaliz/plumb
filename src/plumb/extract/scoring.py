"""Precision/recall over a blind label set, computed before any rule exists.

The selection rule — *which* of a paper's numbers are claims — is measured against
labels it did not author (`labelling.py:1-9`). That measurement is this module: a
rule-agnostic `score(labels, predict)` that compares a rule's opinion — True means
"this candidate is a claim" — against the label a human wrote. It is the instrument,
not the verdict: it turns the blind set into two numbers the rule can fail against,
and it deliberately knows nothing about *how* the opinion was formed (plan D5,
Phase 1).

Three choices here are the point of the module:

**Undefined ratios are `None`, never a silent zero.** Precision needs at least one
predicted positive (`tp+fp > 0`), recall needs at least one positive label
(`tp+fn > 0`). A silent `0.0` would report a rule that never said claim as a perfect
rule, and a rule scored against a label set with no claims as an empty one — either
way the metric the whole slice rests on comes back agreeing with itself (`CLAUDE.md`
#3). The caller reports the `None`; this module never guesses a number for it.

**Division is exact, not binary.** Ratios are `Decimal` divided by `Decimal` — never
`float`, which the AST guard in `tests/extract/test_determinism.py` rejects outright
and which cannot represent `0.1` or `0.6`. Counts are counted first, in integers, and
only then divided, so the ratio is exactly the quotient of the counts.

**The input is read in its own order and left alone.** Labels are iterated in the
order given — a `set` is never built, so nothing hash-ordered reaches the loop — and
the sequence is neither sorted nor modified. Scoring the same labels twice must give
the same `Score`, or the scorer would corrupt the very labels it measures.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from plumb.extract.candidates import Candidate
from plumb.extract.labelling import LABEL_CLAIM, LabelledCandidate

__all__ = [
    "Score",
    "score",
]


@dataclass(frozen=True, slots=True)
class Score:
    """One rule scored against one label set: counts plus the two ratios.

    `precision` is `None` when no positive was predicted (there is nothing to measure
    the rule's positives against) and `recall` is `None` when no label is a claim
    (there is nothing to measure its omissions against) — never `0` by default, so a
    rule that said nothing cannot look like a rule that said nothing right.
    """

    tp: int
    fp: int
    fn: int
    tn: int
    precision: Decimal | None
    recall: Decimal | None


def _divide(numerator: int, denominator: int) -> Decimal:
    """`numerator / denominator` exactly. The caller has already checked `denominator`.

    Integer division via `Decimal` rather than `float`: exact, and the AST guard would
    reject the `float` path in any case. This is the only division the module does,
    and it is the same two lines whichever ratio is asked for.
    """
    return Decimal(numerator) / Decimal(denominator)


def score(
    labels: Sequence[LabelledCandidate],
    predict: Callable[[Candidate], bool],
) -> Score:
    """A rule's opinion against the labels, as counts and exact ratios.

    `predict` is called once per row, in the labels' given order, with that row's
    candidate; True means "claim". The label set is the truth the rule is measured
    against, so a row whose candidate is unlabelled cannot occur here — `load_labels`
    refuses one before this is ever reached.

    An empty label set is refused rather than scored: there are no counts to add and
    nothing to divide, and a silently empty `Score` would read as a pass against a
    blind set that was never built.
    """
    if len(labels) == 0:
        raise ValueError(
            "cannot score an empty label set: a blind set with no rows measures "
            "nothing, and an empty Score would be read as a pass"
        )

    tp = 0
    fp = 0
    fn = 0
    tn = 0
    for entry in labels:
        if predict(entry.candidate):
            if entry.label == LABEL_CLAIM:
                tp += 1
            else:
                fp += 1
        elif entry.label == LABEL_CLAIM:
            fn += 1
        else:
            tn += 1

    precision = (
        _divide(tp, tp + fp) if tp + fp > 0 else None
    )
    recall = (
        _divide(tp, tp + fn) if tp + fn > 0 else None
    )
    return Score(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=precision,
        recall=recall,
    )