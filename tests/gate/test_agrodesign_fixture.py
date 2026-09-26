"""The AgroDesign gate fixture: the paper, and the claims it actually makes (gate-paper G3).

The claim set is defined by a rule fixed before binding (`docs/planning/gate-paper/prd.md`
P2): every numeric cell of Tables 1–8, and every F, p and Shapiro-Wilk value stated in the
prose of §4. Each is a real `Claim` whose reported text occurs **verbatim** at its span in the
normalized paper text — so no curated claim can be a number the paper did not write. Members
of the rule that cannot be represented as a `Claim` are recorded, not dropped.

C1's own recovery on this paper is pinned next to the curated set, so the curated number can
never be read as extraction coverage.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import pytest

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.pipeline import extract_claims
from plumb.extract.value import parse_value
from plumb.pdf import pdf_to_markdown

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gate" / "agrodesign"
PDF_SHA256 = "c2dea137e795ba9f9acc432647d4df3f88b95a3a9c9f5dacfc5c9af8a1abead7"

TABLE_CLAIMS = 75  # every numeric cell of Tables 1–8
PROSE_CLAIMS = 11  # F / p / Shapiro-Wilk values in §4 prose that parse
UNREPRESENTABLE = 2  # "p ¡ 0.001" twice: the PDF renders `<` as `¡`


@pytest.fixture(scope="module")
def paper_text() -> str:
    return normalize_text(pdf_to_markdown((FIXTURE / "paper.pdf").read_bytes()))


def load_claims() -> list[Claim]:
    entries = json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))["claims"]
    return [
        Claim(
            reported_value=parse_value(e["text"]),
            units=None,
            metric=e["metric"],
            location=CharSpan(e["start"], e["end"]),
            artifact_hint=None,
            tolerance_hint=None,
        )
        for e in entries
    ]


def test_the_pdf_is_the_recorded_arxiv_file() -> None:
    data = (FIXTURE / "paper.pdf").read_bytes()
    assert hashlib.sha256(data).hexdigest() == PDF_SHA256
    assert PDF_SHA256 in (FIXTURE / "README.md").read_text(encoding="utf-8")


def test_every_claim_is_grounded_verbatim_at_its_span(paper_text: str) -> None:
    entries = json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))["claims"]
    for entry in entries:
        assert paper_text[entry["start"]:entry["end"]] == entry["text"], entry["metric"]
        assert entry["text"] in entry["context"] and entry["context"] in paper_text


def test_every_claim_parses_and_ids_are_unique() -> None:
    claims = load_claims()
    assert all(c.reported_value is not None for c in claims)
    assert len({c.id for c in claims}) == len(claims)


def test_the_rule_defines_the_count() -> None:
    entries = json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))["claims"]
    kinds = Counter(e["source"] for e in entries)
    assert kinds == {"table": TABLE_CLAIMS, "prose": PROSE_CLAIMS}
    unrepresentable = json.loads(
        (FIXTURE / "unrepresentable.json").read_text(encoding="utf-8")
    )["unrepresentable"]
    assert len(unrepresentable) == UNREPRESENTABLE


def test_unrepresentable_members_are_real_text_that_cannot_parse(paper_text: str) -> None:
    unrepresentable = json.loads(
        (FIXTURE / "unrepresentable.json").read_text(encoding="utf-8")
    )["unrepresentable"]
    for entry in unrepresentable:
        assert paper_text[entry["start"]:entry["end"]] == entry["text"]
        assert parse_value(entry["text"]) is None
        assert entry["reason"]


def test_c1_recovers_none_of_the_curated_claims_today(paper_text: str) -> None:
    # Pinned so an improvement is visible: the C1 follow-on updates this, never silently.
    raw = pdf_to_markdown((FIXTURE / "paper.pdf").read_bytes())
    extracted, rejections = extract_claims(raw)
    curated = {c.id for c in load_claims()}
    assert len({c.id for c in extracted} & curated) == 0
    assert Counter(r.cause for r in rejections) == {"outside_sections": 241, "reference_numeral": 49}
