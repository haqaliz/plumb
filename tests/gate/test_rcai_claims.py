"""The RCAI gate fixture: the rule-encoded claims, grounded verbatim (notebook-paper P2).

The claim set is fixed by the written rule (`tools/rcai_spec.py`; `docs/planning/notebook-paper/prd.md`
P2) and committed before any run: every numeric cell of Table 1 (the four reference
scenarios and the no-RSI baseline — 5 rows × 4 numeric columns) and Table 2 (the three
strategic-market regimes — 3 rows × 3 numeric columns), plus the two unqualified numeric
statistics stated in the results prose (§3.3's no-RSI AGI-to-ASI interval `72`; §4.1's
closed laboratory leading-actor reproduction number `KAA = 1.00`). The prose's eight
approximate statistics (`about` / `approximately` / `≃`) are excluded by the rule: the
paper declines a precise value, so no written-precision reading exists.

Each `reported_value.text` occurs **verbatim** at its span in the normalized paper text —
no claim can be a number the paper did not write — and no claim may be added after the
dev-time run (anti-inflation).
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.value import parse_value
from plumb.pdf import pdf_to_markdown

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gate" / "rcai"

TABLE_1_CLAIMS = 20  # 5 rows × 4 numeric columns (a, T_AGI, T_ASI, ΔT)
TABLE_2_CLAIMS = 9  # 3 rows × 3 numeric columns (T_AGI, T_ASI, ΔT)
PROSE_CLAIMS = 2  # §3.3's `72`; §4.1's `KAA = 1.00` — the unqualified results statistics

TABLE_2_ROUNDINGS = (
    "10.40", "16.53", "6.13", "9.75", "12.58", "2.82", "8.97", "13.42", "4.45",
)


@pytest.fixture(scope="module")
def paper_text() -> str:
    return normalize_text(pdf_to_markdown((FIXTURE / "paper.pdf").read_bytes()))


def load_entries() -> list[dict]:
    return json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))["claims"]


def load_claims() -> list[Claim]:
    return [
        Claim(
            reported_value=parse_value(e["text"]),
            units=None,
            metric=e["metric"],
            location=CharSpan(e["start"], e["end"]),
            artifact_hint=None,
            tolerance_hint=None,
        )
        for e in load_entries()
    ]


def test_every_claim_is_grounded_verbatim_at_its_span(paper_text: str) -> None:
    for entry in load_entries():
        assert paper_text[entry["start"]:entry["end"]] == entry["text"], entry["metric"]
        assert entry["text"] in entry["context"] and entry["context"] in paper_text


def test_every_context_resolves_exactly_once(paper_text: str) -> None:
    for entry in load_entries():
        assert paper_text.count(entry["context"]) == 1, entry["metric"]


def test_the_rule_defines_the_count() -> None:
    entries = load_entries()
    kinds = Counter(e["source"] for e in entries)
    assert kinds == {"table": TABLE_1_CLAIMS + TABLE_2_CLAIMS, "prose": PROSE_CLAIMS}
    table_1 = [e for e in entries if e["metric"].startswith("Table 1 ")]
    table_2 = [e for e in entries if e["metric"].startswith("Table 2 ")]
    assert (len(table_1), len(table_2)) == (TABLE_1_CLAIMS, TABLE_2_CLAIMS)


def test_the_results_prose_contributes_only_the_unqualified_statistics() -> None:
    prose = [e["text"] for e in load_entries() if e["source"] == "prose"]
    assert prose == ["72", "1.00"]


def test_the_market_regimes_are_exactly_as_the_paper_rounded_them() -> None:
    written = [e["text"] for e in load_entries() if e["metric"].startswith("Table 2 ")]
    assert tuple(written) == TABLE_2_ROUNDINGS


def test_every_claim_parses_and_ids_are_unique() -> None:
    claims = load_claims()
    assert all(c.reported_value is not None for c in claims)
    assert len({c.id for c in claims}) == len(claims)
