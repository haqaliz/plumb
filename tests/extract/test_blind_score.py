"""The blind selection score, floored (plan M6, owner decision 2026-09-21).

Pooled precision and recall over the 73 labelled abstract candidates must both
stay at or above `BLIND_SCORE_FLOOR`; a score below the floor forces a rule
revision before merge — the slice can fail.

Honesty note (must be carried into the PR): this is a *conformance* score, not a
validation score. The labels were criteria-drafted from M3/M11 (the owner
delegated the labelling pass), so the rule and the labels share an author and a
perfect score means "the rule implements its criteria" — it does not mean the
criteria are right. Validation against third-party labels is C5's job. The floor
is a regression guard, not a proof.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from plumb.extract.admit import admit
from plumb.extract.candidates import SECTION_ABSTRACT, extract_candidates
from plumb.extract.claim import Claim
from plumb.extract.labelling import load_labels
from plumb.extract.location import normalize_text
from plumb.extract.scoring import score
from plumb.extract.selection import Selected, select

BLIND_SCORE_FLOOR = Decimal("0.90")

PAPERS = sorted(p for p in Path("fixtures/papers").glob("PMC*.md"))
LABELS_DIR = Path("fixtures/labels")


def per_paper_labels() -> list[tuple[str, object, object]]:
    """(document, labels, normalized paper) for each fixture paper."""
    result = []
    for paper in PAPERS:
        document = paper.name.split(".")[0]
        normalized = normalize_text(paper.read_text(encoding="utf-8"))
        abstract = [
            c for c in extract_candidates(normalized)
            if c.section_hint == SECTION_ABSTRACT
        ]
        labels = load_labels(
            (LABELS_DIR / f"{document}.todo.jsonl").read_bytes(),
            candidates=abstract,
            paper=normalized,
            document=document,
        )
        result.append((document, labels, normalized))
    return result


def predicts_claim(candidate: object, normalized: str) -> bool:
    outcome = select(candidate, normalized_text=normalized)
    if not isinstance(outcome, Selected):
        return False
    admitted = admit(
        outcome.candidate,
        normalized_text=normalized,
        metric=outcome.metric,
        units=outcome.units,
    )
    return isinstance(admitted, Claim)


class TestTheBlindScoreIsFloored:
    def test_all_73_labels_load(self) -> None:
        rows = sum(len(labels) for _, labels, _ in per_paper_labels())
        assert rows == 73

    def test_pooled_precision_and_recall_stay_above_the_floor(self) -> None:
        pooled_tp = pooled_fp = pooled_fn = pooled_tn = 0
        for _, labels, normalized in per_paper_labels():
            result = score(
                labels,
                lambda candidate: predicts_claim(candidate, normalized),
            )
            pooled_tp += result.tp
            pooled_fp += result.fp
            pooled_fn += result.fn
            pooled_tn += result.tn

        assert pooled_tp + pooled_fp > 0, "no claim predicted at all"
        assert pooled_tp + pooled_fn > 0, "no claim labelled at all"
        precision = Decimal(pooled_tp) / Decimal(pooled_tp + pooled_fp)
        recall = Decimal(pooled_tp) / Decimal(pooled_tp + pooled_fn)
        assert precision >= BLIND_SCORE_FLOOR, (
            f"pooled precision {precision} fell below the floor "
            f"{BLIND_SCORE_FLOOR} (tp={pooled_tp} fp={pooled_fp})"
        )
        assert recall >= BLIND_SCORE_FLOOR, (
            f"pooled recall {recall} fell below the floor "
            f"{BLIND_SCORE_FLOOR} (tp={pooled_tp} fn={pooled_fn})"
        )