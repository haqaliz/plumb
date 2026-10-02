"""AgroDesign case #1: the benchmark report renders the honest first numbers (Phase 3).

Acceptance criterion 5 of `docs/planning/discrepancy-corpus/benchmark/spec.md` on the
committed gate record, in the in-process `main([...])` pattern
(`tests/gate/test_agrodesign_corpus.py`):

1. The banked case reports coverage 86/86 bound; by-verdict 85 REPRODUCED, 0
   WITHIN-TOLERANCE, 1 DIVERGED, 0 UNVERIFIED; precision 1/1 confirmed; recall 1/1
   (the one labeled claim is the confirmed DIVERGED — `labels.json` carries
   `{DIVERGED_CLAIM_ID: "confirmed"}`).
2. `--json` is canonical and byte-identical across two invocations and across two
   different tmp stores: the content-addressed case_id makes the report bytes
   store-independent.
3. The report bytes carry no worktree or tmp path (the no-local-path pattern).
4. The table form renders the totals row and `1/1 (owner)` rate lines.
"""

from __future__ import annotations

import json
from pathlib import Path

from plumb.cli import main
from test_agrodesign_fixture import FIXTURE

#: The case_id cell renders truncated to 24 code points, `…` when cut (the house rule).
_CASE_ID_WIDTH = 24
_TRUNCATED = 23
_ELLIPSIS = "…"

_WORKTREE = Path(__file__).resolve().parents[2]

#: The case's coverage, per the verdicts the record re-derives (86 claims, 86 bound).
_EXPECTED_COVERAGE = {
    "bound": 86,
    "by_verdict": [
        ["REPRODUCED", 85],
        ["WITHIN-TOLERANCE", 0],
        ["DIVERGED", 1],
        ["UNVERIFIED", 0],
    ],
    "claims": 86,
}


def _bank(store: Path, capsys) -> str:
    """Bank the committed gate record; returns the content-addressed case_id."""
    assert main(["corpus", "bank", str(FIXTURE), "--store", str(store)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    case_id = captured.out.strip().split()[1]
    assert captured.out == f"banked {case_id}\n"
    return case_id


def _cell_id(case_id: str) -> str:
    """The case_id cell: the house truncation rule, 24 code points, `…` when cut."""
    return case_id if len(case_id) <= _CASE_ID_WIDTH else case_id[:_TRUNCATED] + _ELLIPSIS


def _row(
    case_id: str,
    claims: int,
    bound: int,
    reproduced: int,
    within_tolerance: int,
    diverged: int,
    unverified: int,
    labeled: int,
    confirmed: int,
) -> str:
    cells = (
        (_cell_id(case_id), 24),
        (str(claims), 6),
        (str(bound), 5),
        (str(reproduced), 10),
        (str(within_tolerance), 16),
        (str(diverged), 8),
        (str(unverified), 10),
        (str(labeled), 7),
        (str(confirmed), 9),
    )
    return " | ".join(text.ljust(width) for text, width in cells)


class TestTheCaseOneReport:
    """Acceptance 5: the real case's first numbers, via `--json`."""

    def test_coverage_86_of_86_bound_and_1_of_1_rates(self, tmp_path, capsys) -> None:
        store = tmp_path / "store"
        case_id = _bank(store, capsys)
        assert main(["corpus", "report", "--store", str(store), "--json"]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        document = json.loads(captured.out)
        assert document["authority"] == "owner"
        assert [case["case_id"] for case in document["cases"]] == [case_id]
        (case,) = document["cases"]
        assert case["coverage"] == _EXPECTED_COVERAGE
        assert case["diverged"] == 1
        assert case["labeled"] == 1
        assert case["confirmed"] == 1
        assert case["refuted"] == 0
        assert case["precision"] == {"confirmed": 1, "flagged": 1}
        assert case["recall"] == {"confirmed": 1, "flagged": 1}
        totals = document["totals"]
        assert totals["cases"] == 1
        assert totals["coverage"] == _EXPECTED_COVERAGE
        assert totals["diverged"] == 1
        assert totals["labeled"] == 1
        assert totals["confirmed"] == 1
        assert totals["refuted"] == 0
        assert totals["precision"] == {"confirmed": 1, "flagged": 1}
        assert totals["recall"] == {"confirmed": 1, "flagged": 1}

    def test_json_is_byte_identical_across_two_invocations(self, tmp_path, capsys) -> None:
        store = tmp_path / "store"
        _bank(store, capsys)
        argv = ["corpus", "report", "--store", str(store), "--json"]
        assert main(argv) == 0
        first = capsys.readouterr().out
        assert main(argv) == 0
        second = capsys.readouterr().out
        assert second == first
        assert first.endswith("}\n")
        assert not first.endswith("}\n\n")

    def test_json_is_byte_identical_across_two_stores(self, tmp_path, capsys) -> None:
        store_a = tmp_path / "a"
        store_b = tmp_path / "b"
        case_a = _bank(store_a, capsys)
        case_b = _bank(store_b, capsys)
        assert case_a == case_b
        assert main(["corpus", "report", "--store", str(store_a), "--json"]) == 0
        first = capsys.readouterr().out
        assert main(["corpus", "report", "--store", str(store_b), "--json"]) == 0
        second = capsys.readouterr().out
        assert second == first

    def test_the_report_carries_no_local_paths(self, tmp_path, capsys) -> None:
        store = tmp_path / "store"
        _bank(store, capsys)
        assert main(["corpus", "report", "--store", str(store), "--json"]) == 0
        text = capsys.readouterr().out
        assert str(_WORKTREE) not in text, "the report carries the worktree path"
        assert str(tmp_path) not in text, "the report carries a temp path"


class TestTheReportTable:
    """The table form: totals row and the `1/1 (owner)` rate lines."""

    def test_totals_row_and_owner_rate_lines(self, tmp_path, capsys) -> None:
        store = tmp_path / "store"
        case_id = _bank(store, capsys)
        assert main(["corpus", "report", "--store", str(store)]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        lines = captured.out.splitlines()
        assert lines[2] == _row(case_id, 86, 86, 85, 0, 1, 0, 1, 1)
        assert lines[3] == _row("total (1 case)", 86, 86, 85, 0, 1, 0, 1, 1)
        assert lines[4:] == [
            "",
            "  coverage: 86/86 bound",
            "  precision: 1/1 (owner)",
            "  recall: 1/1 (owner)",
        ]