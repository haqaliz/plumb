"""C1's own recovery of the AgroDesign claims, floored (claim-recovery PRD M2, M7).

The curated set (`fixtures/gate/agrodesign/claims.json`) is the label: every numeric cell
of Tables 1–8 and every F, p and Shapiro-Wilk value in §4's prose, grounded verbatim. Here
`extract_claims` runs on the same PDF, with no help, and is scored against it.

**The match is by place and value, not by `Claim.id`** (PRD D2). The id hashes the metric,
and the curated metrics are hand-written (`Table 1 crd ANOVA Treatment DF`); no extractor
could reproduce them. A curated claim is recovered when an extracted claim sits inside its
span and parses to the same value — so the curated `p <0.001` is recovered by the extracted
bound `<0.001` whose metric is `p`.
"""

from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path

import pytest

from plumb.extract.claim import Claim
from plumb.extract.location import normalize_text
from plumb.extract.pipeline import extract_claims
from plumb.extract.value import parse_value
from plumb.pdf import pdf_to_markdown

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gate" / "agrodesign"

RECALL_FLOOR = 0.95
PRECISION_FLOOR = 0.95

#: Extracted claims outside the curated rule that are nonetheless genuine claims of the
#: paper, each with its reason. Precision excludes them from its denominator. Empty:
#: every extracted claim today is either curated or a defect.
GENUINE_OUTSIDE_THE_RULE: frozenset[int] = frozenset()


@pytest.fixture(scope="module")
def run() -> tuple[str, tuple[Claim, ...], list[dict]]:
    raw = pdf_to_markdown((FIXTURE / "paper.pdf").read_bytes())
    claims, _ = extract_claims(raw)
    curated = json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))["claims"]
    return normalize_text(raw), claims, curated


def same_value(a: object, b: object) -> bool:
    """Equal kind and fields, ignoring the verbatim `text`: `p <0.001` and `<0.001`
    are one bound, spelled with and without its name."""
    if type(a) is not type(b):
        return False
    return {f.name: getattr(a, f.name) for f in fields(a) if f.name != "text"} == {
        f.name: getattr(b, f.name) for f in fields(b) if f.name != "text"
    }


def matches(claim: Claim, entry: dict) -> bool:
    inside = entry["start"] <= claim.location.start and claim.location.end <= entry["end"]
    return inside and same_value(claim.reported_value, parse_value(entry["text"]))


def test_recall_meets_the_floor(run) -> None:
    _, claims, curated = run
    missed = [e for e in curated if not any(matches(c, e) for c in claims)]
    recall = (len(curated) - len(missed)) / len(curated)
    assert recall >= RECALL_FLOOR, [(e["metric"], e["text"]) for e in missed]


def test_precision_meets_the_floor(run) -> None:
    text, claims, curated = run
    scored = [c for c in claims if c.location.start not in GENUINE_OUTSIDE_THE_RULE]
    assert scored, "no claims extracted: precision is undefined, and recall has failed"
    extras = [c for c in scored if not any(matches(c, e) for e in curated)]
    precision = (len(scored) - len(extras)) / len(scored)
    assert precision >= PRECISION_FLOOR, [
        (text[c.location.start:c.location.end], c.metric) for c in extras
    ]


def test_no_claim_is_read_from_behind_an_ot1_comparator(run) -> None:
    # `p ¡ 0.001` is `p < 0.001` in LaTeX's OT1 encoding. Its `0.001` as a Point would
    # be a value the paper never wrote.
    text, claims, _ = run
    behind = [
        c for c in claims if text[: c.location.start].rstrip()[-1:] in {"¡", "¿"}
    ]
    assert behind == []


def test_distinct_cells_have_distinct_ids(run) -> None:
    # C4 binds by claim; an id naming two cells (a row's MS and its F) is ambiguous.
    # Before claim-recovery's whitespace-tables aspect, 86 claims carried 79 ids.
    text, claims, _ = run
    by_id: dict[str, list[Claim]] = {}
    for c in claims:
        by_id.setdefault(c.id, []).append(c)
    shared = {
        key: [(text[c.location.start:c.location.end], c.metric) for c in group]
        for key, group in by_id.items()
        if len({c.location for c in group}) > 1
    }
    assert shared == {}
