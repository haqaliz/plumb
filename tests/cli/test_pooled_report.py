"""Pooled `corpus report` over two cases: AgroDesign + a live-banked run (Phase 4).

The first pooled figure of the milestone: one committed gate case (the real
AgroDesign record, `fixtures/gate/agrodesign/`, banked into the test's tmp
store) and one live-banked case (the `tests/cli/fixtures/` repo, banked through
`verify --bank` into the default store `corpus/local`, redirected into the test
by the cwd) — then `corpus report --store <tmp-store>` pools both: per-case
rows, a totals row with denominators (88/88 bound over 88 claims), and the
precision/recall figures carrying their `n/n (owner)` authority markers.

1. `--json` pools 2 cases in sorted case_id order: the AgroDesign case at
   86/86 with 1/1 rates, the live case at 2/2 with no labels (its precision and
   recall are the distinct `None` state, never 0/0); totals 2 cases, 88/88,
   87 REPRODUCED, 1 DIVERGED, labeled 1, precision 1/1, recall 1/1, authority
   "owner".
2. The JSON is canonical and byte-identical across two invocations.
3. The table form renders per-case rows, the `total (2 cases)` row, and the
   denominator-carrying rate lines with the authority markers.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from plumb.cli import main

_THIS_DIR = Path(__file__).parent
_GATE_DIR = _THIS_DIR.parent / "gate"

sys.path.insert(0, str(_GATE_DIR))
from test_agrodesign_fixture import FIXTURE  # noqa: E402

PAPER = _THIS_DIR / "fixtures" / "paper.md"
REPO = _THIS_DIR / "fixtures" / "repo"
BINDINGS = _THIS_DIR / "fixtures" / "bindings.json"

#: The AgroDesign case's numbers, per its committed verdicts (86 claims, 86 bound).
_AGRO_ROW = (86, 86, 85, 0, 1, 0, 1, 1)
#: The live fixture case: 2 claims, both REPRODUCED and bound, no labels.
_LIVE_ROW = (2, 2, 2, 0, 0, 0, 0, 0)

#: The pooled totals, per the two rows above.
_TOTALS_ROW = (88, 88, 87, 0, 1, 0, 1, 1)

#: The case_id cell renders truncated to 24 code points, `…` when cut (the house rule).
_CASE_ID_WIDTH = 24
_TRUNCATED = 23
_ELLIPSIS = "…"


@pytest.fixture
def work_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The CLI's work area for one test: per-test tmp, never the real ~/.plumb-runs."""
    root = tmp_path / "plumb-runs"
    monkeypatch.setattr("plumb.cli.live.WORK_ROOT", root)
    return root


def live_argv(*extra: str) -> list[str]:
    return ["verify", str(PAPER), str(REPO), "--bindings", str(BINDINGS),
            "--no-env-build", *extra]


def _banked_case_id(out: str) -> str:
    """The case id the `banked <case_id>` line on stdout names."""
    return out.rsplit("banked ", 1)[1].strip()


def _cell_id(case_id: str) -> str:
    """The case_id cell: the house truncation rule, 24 code points, `…` when cut."""
    return case_id if len(case_id) <= _CASE_ID_WIDTH else case_id[:_TRUNCATED] + _ELLIPSIS


def _row(case_id: str, claims: int, bound: int, reproduced: int,
         within_tolerance: int, diverged: int, unverified: int,
         labeled: int, confirmed: int) -> str:
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


def _bank_the_two_cases(tmp_path: Path, capsys, work_root: Path) -> tuple[str, str]:
    """Bank the live case into the (cwd-redirected) default store, then AgroDesign.

    Returns `(live_case_id, agro_case_id)`. The live `--bank` uses the default
    store `corpus/local` relative to the cwd — `monkeypatch.chdir(tmp_path)` — so
    the store is `<tmp>/corpus/local`, and the AgroDesign fixture banks into that
    same absolute path via `--store`.
    """
    code = main(live_argv("--bank", "--json"))
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.err == ""
    live_case_id = _banked_case_id(captured.out)

    store = tmp_path / "corpus" / "local"
    assert main(["corpus", "bank", str(FIXTURE), "--store", str(store)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    agro_case_id = captured.out.strip().split()[1]
    assert captured.out == f"banked {agro_case_id}\n"
    return live_case_id, agro_case_id


class TestThePooledJsonReport:
    """Acceptance 1: `--json` pools the two cases with denominators and authority."""

    def test_two_cases_pool_with_denominators(
        self, tmp_path: Path, capsys, work_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        live_case_id, agro_case_id = _bank_the_two_cases(tmp_path, capsys, work_root)
        store = tmp_path / "corpus" / "local"

        assert main(["corpus", "report", "--store", str(store), "--json"]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        document = json.loads(captured.out)
        assert document["authority"] == "owner"
        by_id = {case["case_id"]: case for case in document["cases"]}
        assert sorted(by_id) == sorted((live_case_id, agro_case_id))

        live = by_id[live_case_id]
        assert live["coverage"] == {
            "bound": 2, "by_verdict": [["REPRODUCED", 2], ["WITHIN-TOLERANCE", 0],
                                       ["DIVERGED", 0], ["UNVERIFIED", 0]], "claims": 2,
        }
        assert live["diverged"] == 0
        assert live["labeled"] == 0
        assert live["confirmed"] == 0
        assert live["refuted"] == 0
        assert live["precision"] is None
        assert live["recall"] is None

        agro = by_id[agro_case_id]
        assert agro["coverage"] == {
            "bound": 86, "by_verdict": [["REPRODUCED", 85], ["WITHIN-TOLERANCE", 0],
                                        ["DIVERGED", 1], ["UNVERIFIED", 0]], "claims": 86,
        }
        assert agro["diverged"] == 1
        assert agro["labeled"] == 1
        assert agro["confirmed"] == 1
        assert agro["refuted"] == 0
        assert agro["precision"] == {"confirmed": 1, "flagged": 1}
        assert agro["recall"] == {"confirmed": 1, "flagged": 1}

        totals = document["totals"]
        assert totals["cases"] == 2
        assert totals["coverage"] == {
            "bound": 88, "by_verdict": [["REPRODUCED", 87], ["WITHIN-TOLERANCE", 0],
                                        ["DIVERGED", 1], ["UNVERIFIED", 0]], "claims": 88,
        }
        assert totals["diverged"] == 1
        assert totals["labeled"] == 1
        assert totals["confirmed"] == 1
        assert totals["refuted"] == 0
        assert totals["precision"] == {"confirmed": 1, "flagged": 1}
        assert totals["recall"] == {"confirmed": 1, "flagged": 1}

    def test_json_is_byte_identical_across_two_invocations(
        self, tmp_path: Path, capsys, work_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _bank_the_two_cases(tmp_path, capsys, work_root)
        store = tmp_path / "corpus" / "local"
        argv = ["corpus", "report", "--store", str(store), "--json"]
        assert main(argv) == 0
        first = capsys.readouterr().out
        assert main(argv) == 0
        second = capsys.readouterr().out
        assert second == first
        assert first.endswith("}\n")
        assert not first.endswith("}\n\n")


class TestThePooledReportTable:
    """Acceptance 3: per-case rows, the `total (2 cases)` row, and the rate lines."""

    def test_totals_row_and_owner_rate_lines(
        self, tmp_path: Path, capsys, work_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        live_case_id, agro_case_id = _bank_the_two_cases(tmp_path, capsys, work_root)
        store = tmp_path / "corpus" / "local"

        assert main(["corpus", "report", "--store", str(store)]) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        lines = captured.out.splitlines()
        first_id, second_id = sorted((live_case_id, agro_case_id))
        first_row, second_row = (
            (_LIVE_ROW, _AGRO_ROW) if first_id == live_case_id else (_AGRO_ROW, _LIVE_ROW)
        )
        assert lines[2] == _row(first_id, *first_row)
        assert lines[3] == _row(second_id, *second_row)
        assert lines[4] == _row("total (2 cases)", *_TOTALS_ROW)
        assert lines[5:] == [
            "",
            "  coverage: 88/88 bound",
            "  precision: 1/1 (owner)",
            "  recall: 1/1 (owner)",
        ]