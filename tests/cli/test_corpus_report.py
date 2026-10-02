"""corpus report: `plumb corpus report [--store DIR] [--authority ...] [--json]` (Phase 2).

Acceptance criteria 3, 4 and 6 of `docs/planning/discrepancy-corpus/benchmark/spec.md`
and design decisions 6-7 of `benchmark/plan_20261001.md`, written failing first
against the shell, in the in-process `main([...])` pattern:

1. A store of banked cases reports a fixed-layout table: per-case rows (case_id,
   claims, bound, by-verdict counts, labeled DIVERGEDs, confirmed), a totals row,
   and coverage / precision / recall lines with denominators and the `(owner)`
   authority; exit 0, empty stderr.
2. `--json` emits canonical bytes (sorted keys, one trailing newline) carrying the
   authority field, byte-identical across two invocations, with no machine path.
3. `--authority third-party` renders `(third-party)` in the table and
   `"authority":"third-party"` in the JSON.
4. A tampered case member refuses the whole report: exit 1, `CORPUS_REFUSED`,
   stderr names the case and cause; never a traceback.
5. A missing store dir is `CORPUS_REFUSED`; an empty store reports zeros and no
   rates (`no labeled DIVERGEDs` / `no labeled claims`), exit 0.
6. `plumb corpus` bare and an unknown `--authority` value are usage errors
   (exit 2); a subdirectory without `case.json` is not a case.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from plumb.cli import CORPUS_REFUSED, main
from plumb.corpus import bank_case
from plumb.corpus.metrics import DIVERGED, REPRODUCED, UNVERIFIED

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent / "corpus"))
from record_helpers import record_dir  # noqa: E402

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}

#: The table's pinned column layout, as the renderer defines it.
_HEADER = " | ".join(
    name.ljust(width)
    for name, width in (
        ("CASE", 24),
        ("CLAIMS", 6),
        ("BOUND", 5),
        ("REPRODUCED", 10),
        ("WITHIN-TOLERANCE", 16),
        ("DIVERGED", 8),
        ("UNVERIFIED", 10),
        ("LABELED", 7),
        ("CONFIRMED", 9),
    )
)
_SEPARATOR = "-" * 119


def _rows(*verdicts: tuple[str, str]) -> list[tuple[str, str, bool]]:
    return [(claim_id, verdict, verdict != UNVERIFIED) for claim_id, verdict in verdicts]


def _verdicts_bytes(rows: list[tuple[str, str, bool]], run_id: str = "run-1") -> bytes:
    document = {
        "run_id": run_id,
        "coverage": {
            "claims": len(rows),
            "bound": sum(bound for _, _, bound in rows),
            "by_verdict": {},
            "by_cause": {},
        },
        "verdicts": [
            {"claim_id": claim_id, "verdict": verdict, "bound": bound}
            for claim_id, verdict, bound in rows
        ],
    }
    return (json.dumps(document, **_JSON) + "\n").encode("utf-8")


def _claim_id(record: Path) -> str:
    """The single claim's id, from the record's own bindings lane."""
    document = json.loads((record / "bindings.json").read_bytes())
    return document["bindings"][0]["claim_id"]


def _cell_id(case_id: str) -> str:
    """The case_id cell: the house truncation rule, 24 code points, `…` when cut."""
    return case_id if len(case_id) <= 24 else case_id[:23] + "…"


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


def _banked(store: Path, root: Path, capsys, labels: bytes | None = None) -> str:
    """One CLI-banked record (the replay-validated bank path); returns the case id."""
    record = record_dir(root, labels=labels)
    assert main(["corpus", "bank", str(record), "--store", str(store)]) == 0
    return capsys.readouterr().out.strip().split()[1]


def _crafted_case(store: Path, root: Path) -> str:
    """A case banked directly with hand-written verdicts (diverged + unverified)."""
    record = record_dir(root)
    (record / "verdicts.json").write_bytes(
        _verdicts_bytes(
            _rows(
                ("c1", DIVERGED),
                ("c2", DIVERGED),
                ("c3", REPRODUCED),
                ("c4", UNVERIFIED),
            )
        )
    )
    case = bank_case(record, store, labels={"c1": "confirmed", "c2": "refuted"})
    return case.case_id


def _store(tmp_path: Path, capsys) -> tuple[Path, str, str, str]:
    """The three-case store the table tests report over.

    One plain CLI-banked record, one CLI-banked record with a record-side label
    (a labeled non-DIVERGED claim: flagged for recall, never precision), and one
    case banked directly with hand-written verdicts (2 DIVERGED, 1 REPRODUCED,
    1 UNVERIFIED) and labels confirming one DIVERGED and refuting the other.
    Returns `(store, plain_id, labeled_id, crafted_id)`.
    """
    store = tmp_path / "store"
    plain = _banked(store, tmp_path / "plain", capsys)
    claim_id = _claim_id(tmp_path / "plain" / "record")
    labels = f'{{"{claim_id}":"confirmed"}}\n'.encode()
    labeled = _banked(store, tmp_path / "labeled", capsys, labels=labels)
    crafted = _crafted_case(store, tmp_path / "crafted")
    return store, plain, labeled, crafted


class TestReportShowsPerCaseRowsAndTotals:
    """Acceptance 1: fixed-layout table, per-case rows + totals with authority."""

    def test_the_table_rows_totals_and_rate_lines(self, tmp_path: Path, capsys) -> None:
        store, plain, labeled, crafted = _store(tmp_path, capsys)
        code = main(["corpus", "report", "--store", str(store)])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        lines = captured.out.splitlines()
        assert lines[0] == _HEADER
        assert lines[1] == _SEPARATOR
        rows = lines[2:5]
        expected = {
            _cell_id(plain): _row(plain, 1, 1, 1, 0, 0, 0, 0, 0),
            _cell_id(labeled): _row(labeled, 1, 1, 1, 0, 0, 0, 0, 0),
            _cell_id(crafted): _row(crafted, 4, 3, 1, 0, 2, 1, 2, 1),
        }
        assert {row[:24].rstrip(): row for row in rows} == expected
        assert [row[:24].rstrip() for row in rows] == sorted(expected)
        assert lines[5] == _row("total (3 cases)", 6, 5, 3, 0, 2, 1, 2, 1)
        assert lines[6:] == [
            "",
            "  coverage: 5/6 bound",
            "  precision: 1/2 (owner)",
            "  recall: 1/3 (owner)",
        ]
        assert captured.out.endswith("\n")


class TestReportJsonIsCanonical:
    """Acceptance 2: `--json` bytes are canonical, path-free, and repeatable."""

    def test_json_bytes_are_canonical_and_byte_identical(self, tmp_path: Path, capsys) -> None:
        store, plain, labeled, crafted = _store(tmp_path, capsys)
        argv = ["corpus", "report", "--store", str(store), "--json"]
        assert main(argv) == 0
        first = capsys.readouterr().out
        assert main(argv) == 0
        second = capsys.readouterr().out
        assert second == first
        assert first.endswith("}\n")
        assert not first.endswith("}\n\n")
        document = json.loads(first)
        assert document["authority"] == "owner"
        assert [case["case_id"] for case in document["cases"]] == sorted(
            [plain, labeled, crafted]
        )
        assert document["totals"]["cases"] == 3
        assert document["totals"]["coverage"] == {
            "bound": 5,
            "by_verdict": [
                ["REPRODUCED", 3],
                ["WITHIN-TOLERANCE", 0],
                ["DIVERGED", 2],
                ["UNVERIFIED", 1],
            ],
            "claims": 6,
        }
        assert document["totals"]["diverged"] == 2
        assert document["totals"]["labeled"] == 3
        assert document["totals"]["confirmed"] == 1
        assert document["totals"]["refuted"] == 1
        assert document["totals"]["precision"] == {"confirmed": 1, "flagged": 2}
        assert document["totals"]["recall"] == {"confirmed": 1, "flagged": 3}
        assert str(store) not in first

    def test_each_case_carries_its_counts_and_rates(self, tmp_path: Path, capsys) -> None:
        store, _plain, _labeled, crafted = _store(tmp_path, capsys)
        assert main(["corpus", "report", "--store", str(store), "--json"]) == 0
        document = json.loads(capsys.readouterr().out)
        by_id = {case["case_id"]: case for case in document["cases"]}
        assert by_id[crafted] == {
            "case_id": crafted,
            "confirmed": 1,
            "coverage": {
                "bound": 3,
                "by_verdict": [
                    ["REPRODUCED", 1],
                    ["WITHIN-TOLERANCE", 0],
                    ["DIVERGED", 2],
                    ["UNVERIFIED", 1],
                ],
                "claims": 4,
            },
            "diverged": 2,
            "labeled": 2,
            "precision": {"confirmed": 1, "flagged": 2},
            "recall": {"confirmed": 1, "flagged": 2},
            "refuted": 1,
        }


class TestTheAuthorityIsAReportTimeDeclaration:
    """Acceptance 3: `--authority third-party` renders in table and JSON."""

    def test_third_party_renders_in_the_table(self, tmp_path: Path, capsys) -> None:
        store, _plain, _labeled, crafted = _store(tmp_path, capsys)
        assert main(
            ["corpus", "report", "--store", str(store), "--authority", "third-party"]
        ) == 0
        out = capsys.readouterr().out
        assert "  precision: 1/2 (third-party)" in out
        assert "  recall: 1/3 (third-party)" in out
        assert "owner" not in out

    def test_third_party_renders_in_the_json(self, tmp_path: Path, capsys) -> None:
        store, *_ = _store(tmp_path, capsys)
        assert main(
            [
                "corpus", "report", "--store", str(store),
                "--authority", "third-party", "--json",
            ]
        ) == 0
        assert '"authority":"third-party"' in capsys.readouterr().out


class TestATamperedCaseRefusesTheReport:
    """Acceptance 4: a stored member that no longer matches its hash refuses all."""

    def test_a_tampered_verdicts_refuses_and_names_the_case(
        self, tmp_path: Path, capsys
    ) -> None:
        store = tmp_path / "store"
        case_id = _banked(store, tmp_path / "record", capsys)
        path = store / case_id / "verdicts.json"
        data = bytearray(path.read_bytes())
        data[0] ^= 0x01
        path.write_bytes(bytes(data))
        code = main(["corpus", "report", "--store", str(store)])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {CORPUS_REFUSED}: ")
        assert case_id in captured.err
        assert "verdicts" in captured.err
        assert "Traceback" not in captured.err


class TestStoreFailuresAreNamed:
    """Acceptance 5: a missing store is refused; an empty store reports zeros."""

    def test_a_missing_store_dir_is_refused(self, tmp_path: Path, capsys) -> None:
        code = main(["corpus", "report", "--store", str(tmp_path / "no-store")])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {CORPUS_REFUSED}: ")
        assert "Traceback" not in captured.err

    def test_an_empty_store_reports_zeros_and_no_rates(self, tmp_path: Path, capsys) -> None:
        store = tmp_path / "store"
        store.mkdir()
        code = main(["corpus", "report", "--store", str(store)])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        lines = captured.out.splitlines()
        assert lines[0] == _HEADER
        assert lines[1] == _SEPARATOR
        assert lines[2] == _row("total (0 cases)", 0, 0, 0, 0, 0, 0, 0, 0)
        assert lines[3:] == [
            "",
            "  coverage: 0/0 bound",
            "  precision: no labeled DIVERGEDs",
            "  recall: no labeled claims",
        ]

    def test_an_empty_store_json_carries_zeros_and_null_rates(
        self, tmp_path: Path, capsys
    ) -> None:
        store = tmp_path / "store"
        store.mkdir()
        assert main(["corpus", "report", "--store", str(store), "--json"]) == 0
        document = json.loads(capsys.readouterr().out)
        assert document["cases"] == []
        assert document["totals"]["cases"] == 0
        assert document["totals"]["coverage"] == {
            "bound": 0,
            "by_verdict": [
                ["REPRODUCED", 0],
                ["WITHIN-TOLERANCE", 0],
                ["DIVERGED", 0],
                ["UNVERIFIED", 0],
            ],
            "claims": 0,
        }
        assert document["totals"]["precision"] is None
        assert document["totals"]["recall"] is None


class TestUsageAndCaseDiscovery:
    """Acceptance 6: usage exits 2; only `case.json` directories are cases."""

    def test_corpus_without_a_subcommand_is_a_usage_error(self, capsys) -> None:
        code = main(["corpus"])
        assert code == 2
        assert "Traceback" not in capsys.readouterr().err

    def test_an_unknown_authority_value_is_a_usage_error(self, capsys) -> None:
        code = main(["corpus", "report", "--authority", "bogus"])
        assert code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "bogus" in captured.err
        assert "Traceback" not in captured.err

    def test_a_directory_without_case_json_is_not_a_case(self, tmp_path: Path, capsys) -> None:
        store = tmp_path / "store"
        case_id = _banked(store, tmp_path / "record", capsys)
        (store / "notes").mkdir()
        (store / "notes" / "scratch.txt").write_text("not a case\n", encoding="utf-8")
        assert main(["corpus", "report", "--store", str(store)]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert lines[2] == _row(case_id, 1, 1, 1, 0, 0, 0, 0, 0)
        assert lines[3] == _row("total (1 case)", 1, 1, 1, 0, 0, 0, 0, 0)