"""C1's own recovery of the Perrin claims, measured and reported (panel-run P2).

The curated set (`fixtures/gate/perrin/claims.json`) is the label: every numeric cell
of Table 1's p=20 and p=100 columns, grounded verbatim. Here `extract_claims` runs on
the same PDF, with no help, and is scored against it by **place and value** (never by
`Claim.id` — the id hashes the hand-written metric). The full rule (curated + the 217
runtime-gated `unrepresentable.json` members) is the paper's actual numeric-cell set;
precision is measured against it, so the runtime-gated cells count as true positives,
never defects.

Measured 2026-10-02: **recall 1.000** (16/16 curated recovered), **precision 0.207**
(103/498 extracted claims are real paper cells; the 395 extras are layout numerals —
β coefficients, section numbers, list markers). The numbers are reported as measured
in the fixture README; they are not tuned to a floor (`docs/technical/CAPABILITY_ROADMAP.md`
C1 claim-recovery framing).
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

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gate" / "perrin"

RECALL = 1.0  # 16/16 curated cells recovered, place+value
PRECISION = 0.207  # 103/498 against the full rule (curated + runtime-gated members)


@pytest.fixture(scope="module")
def run() -> tuple[str, tuple[Claim, ...], list[dict], list[dict]]:
    raw = pdf_to_markdown((FIXTURE / "paper.pdf").read_bytes())
    claims, _ = extract_claims(raw)
    curated = json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))["claims"]
    unrepresentable = json.loads(
        (FIXTURE / "unrepresentable.json").read_text(encoding="utf-8")
    )["unrepresentable"]
    return normalize_text(raw), claims, curated, curated + unrepresentable


def same_value(a: object, b: object) -> bool:
    """Equal kind and fields, ignoring the verbatim `text`."""
    if type(a) is not type(b):
        return False
    return {f.name: getattr(a, f.name) for f in fields(a) if f.name != "text"} == {
        f.name: getattr(b, f.name) for f in fields(b) if f.name != "text"
    }


def matches(claim: Claim, entry: dict) -> bool:
    inside = entry["start"] <= claim.location.start and claim.location.end <= entry["end"]
    return inside and same_value(claim.reported_value, parse_value(entry["text"]))


def test_recall_is_measured_and_documented(run) -> None:
    _, claims, curated, _ = run
    missed = [e for e in curated if not any(matches(c, e) for c in claims)]
    recall = (len(curated) - len(missed)) / len(curated)
    readme = (FIXTURE / "README.md").read_text(encoding="utf-8")
    assert f"recall | {recall:.3f}" in readme, (
        f"recovery not documented: recall {recall:.3f} (missed: {[e['metric'] for e in missed]})"
    )
    assert recall == RECALL


def test_precision_is_measured_against_the_full_rule_and_documented(run) -> None:
    text, claims, _, rule = run
    inside_rule = [c for c in claims if any(matches(c, e) for e in rule)]
    precision = len(inside_rule) / len(claims)
    extras = [c for c in claims if not any(matches(c, e) for e in rule)]
    readme = (FIXTURE / "README.md").read_text(encoding="utf-8")
    assert f"precision | {precision:.3f}" in readme, (
        f"precision not documented: {precision:.3f} ({len(claims)} extracted, "
        f"{len(inside_rule)} in the rule; layout extras include: "
        f"{[repr(text[c.location.start:c.location.end]) for c in extras[:8]]})"
    )
    assert precision == pytest.approx(PRECISION, abs=0.001)


def test_a_shared_id_never_carries_different_values(run) -> None:
    # Repeated layout/spec numerals ("500", "0.5") share ids by value-identity dedup —
    # that is the record layer's contract, not the AgroDesign ambiguity defect (two
    # different values under one id). Pin the distinction: a shared id spans locations
    # whose parsed values are all equal.
    text, claims, _, _ = run
    by_id: dict[str, list[Claim]] = {}
    for c in claims:
        by_id.setdefault(c.id, []).append(c)
    shared = {k: g for k, g in by_id.items() if len({c.location for c in g}) > 1}
    for group in shared.values():
        values = {same_value(a.reported_value, b.reported_value) for a, b in
                  zip(group, group[1:])}
        assert False not in values and values, (
            "a shared id carries different values: "
            f"{[(text[c.location.start:c.location.end], c.metric) for c in group]}"
        )