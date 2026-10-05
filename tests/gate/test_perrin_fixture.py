"""The Perrin gate fixture: the paper, and the claims its rule defines (panel-run P2).

The claim set is defined by a rule fixed before any run or binding
(`fixtures/gate/perrin/README.md`): every numeric performance cell of the paper's
main-text Tables 1-4, gated by the panel's dev-time runtime budget — Table 1's p=20
and p=100 columns (16 cells) are claims; the p=1000 column and Tables 2-4 (217 cells)
are cluster-scale on this machine and are recorded non-claims with the measured reason.
Each claim's reported text occurs **verbatim** at its span in the normalized paper text.

C1's own recovery on this paper is measured and reported next to the curated set, so the
curated number can never be read as extraction coverage.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import pytest

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.value import parse_value
from plumb.pdf import pdf_to_markdown

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gate" / "perrin"
PDF_SHA256 = "f40dd4124c16b2c37d929fa1f1f2936c8d69816c58dcf94aff2da817e909144c"

TABLE_CLAIMS = 16  # Table 1, p=20 (9) + p=100 (7) columns
UNREPRESENTABLE = 217  # Table 1 p=1000 + Tables 2-4: beyond the panel's laptop-CPU budget


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
    assert kinds == {"table": TABLE_CLAIMS}
    unrepresentable = json.loads(
        (FIXTURE / "unrepresentable.json").read_text(encoding="utf-8")
    )["unrepresentable"]
    assert len(unrepresentable) == UNREPRESENTABLE


def test_unrepresentable_members_are_grounded_with_a_measured_reason(
    paper_text: str,
) -> None:
    unrepresentable = json.loads(
        (FIXTURE / "unrepresentable.json").read_text(encoding="utf-8")
    )["unrepresentable"]
    for entry in unrepresentable:
        assert paper_text[entry["start"]:entry["end"]] == entry["text"]
        assert parse_value(entry["text"]) is not None  # representable values, not parse-failures
        assert "CPU-hours" in entry["reason"] and entry["reason"]