"""Tests for the precision/recall scorer that will measure the selection rule.

The scorer is the instrument, not the measurement. The plan (D5, Phase 1) keeps it
rule-agnostic on purpose: `score(labels, predict)` compares a *rule's* opinion —
`predict(candidate)` is True when the rule calls the candidate a claim — against the
labels a human wrote first. The ordering is load-bearing (`labelling.py:7-9`): the
labels are committed before any rule exists, and the scorer is what turns them into a
number the rule can fail against.

Three properties are under test here, and each is a guardrail rather than a detail:

- **Undefined is `None`, never a silent zero.** `tp+fp == 0` (no positives predicted)
  makes precision undefined; `tp+fn == 0` (no positive labels) makes recall undefined.
  A silent `0.0` would report a rule that said nothing as a perfect rule — the metric
  the whole slice rests on agreeing with itself (`CLAUDE.md` #3).
- **Exact Decimal arithmetic.** Counts are integers and the ratios are computed with
  `Decimal`, never `float` — the AST guard in `test_determinism.py` rejects the float
  path, and an exact `0.75` is assertable where a binary approximation is not.
- **The input is read, not consumed.** Scoring the same labels twice yields the same
  `Score`, and the labels sequence arrives unchanged — a scorer that mutated or
  reordered the blind set would corrupt the very labels it measures.

No test here emits a verdict, and none decides whether a candidate *is* a claim.
"""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from plumb.extract.candidates import (
    SECTION_RESULTS,
    Candidate,
)
from plumb.extract.labelling import (
    LABEL_CLAIM,
    LABEL_NOT_CLAIM,
    LabelledCandidate,
)
from plumb.extract.location import CharSpan
from plumb.extract.scoring import Score, score


def labelled(text: str, label: str) -> LabelledCandidate:
    """One labelled row: a minimal candidate, hand-labelled by a human."""
    return LabelledCandidate(
        row_id=f"row-{text}",
        candidate=Candidate(
            text=text,
            span=CharSpan(0, len(text)),
            context=f"AUC was {text}.",
            section_hint=SECTION_RESULTS,
        ),
        label=label,
    )


def predict_claims(*texts: str) -> Callable[[Candidate], bool]:
    """A rule stand-in: calls `text` a claim, everything else not a claim.

    The rule will read the same `Candidate` fields this reads; nothing about the
    scorer cares how the opinion is formed, only that True means "claim".
    """
    claimed = frozenset(texts)

    def predict(candidate: Candidate) -> bool:
        return candidate.text in claimed

    return predict


class TestPerfectPrediction:
    """Every prediction agrees with every label: nothing to catch, nothing missed."""

    def test_all_predictions_correct_gives_exact_counts_and_ratio_one(self) -> None:
        labels = [
            labelled("0.87", LABEL_CLAIM),
            labelled("0.92", LABEL_CLAIM),
            labelled("2019", LABEL_NOT_CLAIM),
            labelled("412", LABEL_NOT_CLAIM),
        ]
        expected = Score(
            tp=2,
            fp=0,
            fn=0,
            tn=2,
            precision=Decimal("1"),
            recall=Decimal("1"),
        )
        assert score(labels, predict_claims("0.87", "0.92")) == expected


class TestMixedPredictions:
    """Real rules are not perfect; the counts and ratios must be exact, not close."""

    def test_mixed_predictions_give_hand_computed_counts_and_ratios(self) -> None:
        # Three claims called claims, two claims missed, one not-claim called a claim,
        # two not-claims correctly passed over. Hand-computed:
        #   precision = tp/(tp+fp) = 3/4 = 0.75
        #   recall    = tp/(tp+fn) = 3/5 = 0.6
        labels = [
            labelled("0.87", LABEL_CLAIM),
            labelled("0.92", LABEL_CLAIM),
            labelled("0.75", LABEL_CLAIM),
            labelled("0.10", LABEL_CLAIM),
            labelled("0.50", LABEL_CLAIM),
            labelled("12", LABEL_NOT_CLAIM),
            labelled("2019", LABEL_NOT_CLAIM),
            labelled("34", LABEL_NOT_CLAIM),
        ]
        expected = Score(
            tp=3,
            fp=1,
            fn=2,
            tn=2,
            precision=Decimal("0.75"),
            recall=Decimal("0.6"),
        )
        assert (
            score(labels, predict_claims("0.87", "0.92", "0.75", "12"))
            == expected
        )


class TestNoPositivesPredicted:
    """A rule that never says claim has no precision — and must not be handed a 0."""

    def test_precision_is_none_and_recall_is_zero_when_nothing_is_predicted(self) -> None:
        labels = [
            labelled("0.87", LABEL_CLAIM),
            labelled("0.92", LABEL_CLAIM),
            labelled("2019", LABEL_NOT_CLAIM),
        ]
        predicted = score(labels, predict_claims())
        assert predicted.tp == 0
        assert predicted.fp == 0
        assert predicted.fn == 2
        assert predicted.tn == 1
        assert predicted.precision is None
        assert predicted.recall == Decimal("0")


class TestNoPositiveLabels:
    """A label set with no claims makes recall undefined — the honest `None`."""

    def test_precision_is_zero_and_recall_is_none_when_no_label_is_a_claim(self) -> None:
        labels = [
            labelled("12", LABEL_NOT_CLAIM),
            labelled("2019", LABEL_NOT_CLAIM),
            labelled("412", LABEL_NOT_CLAIM),
        ]
        predicted = score(labels, predict_claims("12", "2019"))
        assert predicted.tp == 0
        assert predicted.fp == 2
        assert predicted.fn == 0
        assert predicted.tn == 1
        assert predicted.precision == Decimal("0")
        assert predicted.recall is None


class TestEmptyLabels:
    def test_an_empty_label_set_is_refused(self) -> None:
        # Nothing to count, so nothing to divide; a silently empty score would read
        # as a pass against a label set that was never built.
        with pytest.raises(ValueError, match="empty"):
            score([], predict_claims("0.87"))


class TestDeterminism:
    def test_scoring_the_same_labels_twice_yields_equal_scores(self) -> None:
        labels = [
            labelled("0.87", LABEL_CLAIM),
            labelled("0.92", LABEL_CLAIM),
            labelled("12", LABEL_NOT_CLAIM),
        ]
        predict = predict_claims("0.87")
        assert score(labels, predict) == score(labels, predict)

    def test_scoring_does_not_mutate_or_reorder_the_input(self) -> None:
        labels = [
            labelled("0.87", LABEL_CLAIM),
            labelled("12", LABEL_NOT_CLAIM),
            labelled("0.92", LABEL_CLAIM),
        ]
        snapshot = list(labels)
        score(labels, predict_claims("0.87"))
        assert labels == snapshot