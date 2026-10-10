"""C1's own recovery of the RCAI claims, measured and reported (notebook-paper G4).

The curated set (`fixtures/gate/rcai/claims.json`) is the label: every numeric cell of
Table 1 and Table 2, plus the unqualified results-prose statistics, all grounded verbatim
at their spans. Here `extract_claims` runs on the same PDF, with no help, and is scored
against it by **place and value** — the AgroDesign convention (`test_agrodesign_recovery.py`):
a curated claim is recovered when an extracted claim sits inside its span and parses to the
same value, never by `Claim.id` (which hashes the hand-written metric).

The number is a conformance report on a curated rule, not coverage and not a pass/fail
gate: the fixture's claim set is rule-encoded (P2), and C1's own extraction is scored
against it here as one more honest measurement. The measured number and its interpretation
are recorded in the fixture README under "C1 conformance", and this test pins that the
README states the measured number.
"""

from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path

import pytest

from plumb.extract.claim import Claim
from plumb.extract.pipeline import extract_claims
from plumb.extract.value import parse_value
from plumb.pdf import pdf_to_markdown

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gate" / "rcai"


@pytest.fixture(scope="module")
def run() -> tuple[tuple[Claim, ...], list[dict]]:
    raw = pdf_to_markdown((FIXTURE / "paper.pdf").read_bytes())
    claims, _ = extract_claims(raw)
    curated = json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))["claims"]
    return claims, curated


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


def recovered_count(claims: tuple[Claim, ...], curated: list[dict]) -> int:
    return sum(any(matches(c, e) for c in claims) for e in curated)


def test_recovery_is_a_reported_number(run, capsys) -> None:
    claims, curated = run
    recovered = recovered_count(claims, curated)
    print(
        f"C1 conformance: {recovered}/{len(curated)} curated claim values recovered "
        f"from {len(claims)} extracted claims"
    )
    assert 0 <= recovered <= len(curated)


def test_the_recovery_number_is_recorded_in_the_readme(run) -> None:
    claims, curated = run
    recovered = recovered_count(claims, curated)
    readme = " ".join((FIXTURE / "README.md").read_text(encoding="utf-8").split())
    assert f"recovers {recovered} of {len(curated)} curated claim values" in readme
