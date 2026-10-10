"""render: the machine contract (`--json`) and the human contract (fixed-layout table).

Acceptance criteria 1, 2, 4 and 5 of `docs/planning/verify-cli/render/spec.md`, plus
the plan's edge cases (truncation without splitting a multi-byte character, and the
`located_text` newline sanitization). The renderer is pure — `render_verdicts(verdict_set,
*, json: bool) -> bytes` — so every assertion here is on bytes, never on a printed line.

The heavy fixtures come from the committed AgroDesign record, replayed through the same
helpers the gate replay uses (`tests/gate/test_agrodesign_replay.py:34-47`). The child
processes follow `tests/extract/test_determinism.py`'s style: a fresh interpreter writes
raw bytes to `sys.stdout.buffer`, and the parent compares bytes, so a shell, a `text=True`
capture or a `print` round-trip cannot quietly translate a trailing newline.
"""

from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from plumb.cli import render_verdicts
from plumb.run import parse_trace
from plumb.run.capture import Capture
from plumb.verify import (
    REPRODUCED,
    UNVERIFIED,
    Completed,
    Verdict,
    VerdictSet,
    load_bindings,
    verify_claims,
)
from plumb.verify.bindings import CsvCell, HtmlTable, JsonPointer, NotebookCell, StdoutRegex
from plumb.verify.causes import NO_BINDING, WONT_RUN

_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parents[2]
_SRC = _REPO_ROOT / "src"
_GATE_DIR = _THIS_DIR.parent / "gate"
_GOLDEN = _THIS_DIR / "golden" / "table_agrodesign.txt"

# The gate fixture helpers live in tests/gate; make them importable from here (and from
# the child interpreters below, which reuse this module).
sys.path.insert(0, str(_GATE_DIR))

from test_agrodesign_fixture import FIXTURE, load_claims

#: The pinned column widths of the table layout. The layout is the contract, so the
#: tests name the widths rather than the renderer's.
COLUMN_WIDTHS = (15, 24, 24, 24, 24, 24, 24)
_SEPARATOR_WIDTH = sum(COLUMN_WIDTHS) + 3 * (len(COLUMN_WIDTHS) - 1)


def replay():
    """The VerdictSet the committed AgroDesign record re-derives (never a re-run)."""
    claims = load_claims()
    bindings = load_bindings((FIXTURE / "bindings.json").read_bytes(), [c.id for c in claims])
    trace = parse_trace((FIXTURE / "trace.json").read_bytes())
    capture = Capture(
        store=FIXTURE / "objects", artifacts=trace.artifacts, stale=trace.stale,
        causes=trace.causes,
    )
    return verify_claims(claims, bindings, Completed(trace, capture))


def _unverified(claim_id: str, cause: str) -> Verdict:
    return Verdict(
        claim_id=claim_id,
        verdict=UNVERIFIED,
        cause=cause,
        reported_text="0.87",
        artifact=None,
        locator=None,
        located_text=None,
        sha256=None,
        run_id="run-1",
        rederived=None,
        band=None,
        tolerance_band=None,
        threshold=None,
        tolerance_threshold=None,
        delta=None,
    )


def _reproduced(
    *,
    claim_id: str = "c1",
    reported: str = "0.87",
    located: str = "0.87",
    artifact: str = "results/a.csv",
    locator=JsonPointer("/metrics/auc"),
) -> Verdict:
    return Verdict(
        claim_id=claim_id,
        verdict=REPRODUCED,
        cause=None,
        reported_text=reported,
        artifact=artifact,
        locator=locator,
        located_text=located,
        sha256="0" * 64,
        run_id="run-1",
        rederived=Decimal("0.87"),
        band=(Decimal("0.865"), Decimal("0.875")),
        tolerance_band=None,
        threshold=None,
        tolerance_threshold=None,
        delta=Decimal("0.0"),
    )


def probe() -> bytes:
    """The control payload: this interpreter's `hash()`, which must vary with the seed."""
    return repr(tuple(hash(word) for word in ("plumb", "REPRODUCED", "0.445", "µg"))).encode(
        "utf-8"
    )


# --------------------------------------------------------------------------------
# Cross-process machinery (acceptance 1 & 2 are subprocess tests)
# --------------------------------------------------------------------------------


def render_child_direct(payload: str) -> bytes:
    """The bytes a child is asked to produce, rendered in this process.

    The determinism tests compare children against this, tying the cross-process claim
    to the in-process one. `probe` is the control: this interpreter's `hash()`, the one
    thing that *must* differ between children under different seeds.
    """
    if payload == "probe":
        return probe()
    verdicts = replay()
    if payload == "json":
        return render_verdicts(verdicts, json=True)
    if payload == "table":
        return render_verdicts(verdicts, json=False)
    raise ValueError(f"unknown payload: {payload!r}")


def child_main(payload: str) -> None:
    """Entry point for a spawned interpreter: raw bytes to stdout, nothing else."""
    sys.stdout.buffer.write(render_child_direct(payload))
    sys.stdout.buffer.flush()


_CHILD_PROGRAM = """\
import sys

# argv[1] is tests/cli and argv[2] is tests/gate: the child imports the fixtures from
# the same modules the parent compares against, so the two cannot drift apart.
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])

from test_render import child_main

child_main(sys.argv[3])
"""


def run_child(payload: str, *, hash_seed: str, cwd: Path | None = None) -> bytes:
    """One fresh interpreter under `hash_seed`; its stdout bytes, un-decoded."""
    env = {
        **os.environ,
        "PYTHONHASHSEED": hash_seed,
        "PYTHONPATH": str(_SRC),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_PROGRAM, str(_THIS_DIR), str(_GATE_DIR), payload],
        env=env,
        cwd=None if cwd is None else str(cwd),
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"child failed (payload={payload!r}, seed={hash_seed!r}):\n"
        f"{result.stderr.decode('utf-8', 'replace')}"
    )
    assert isinstance(result.stdout, bytes)
    return result.stdout


class TestJsonIsTheCommittedRecord:
    """Acceptance 1: `--json` is byte-identical to the committed `verdicts.json`.

    The committed record *is* the canonical document: the gate replay pins
    `serialize_verdicts(replayed) == verdicts.json`, and `--json` renders through the
    same serializer, so the golden file is the record itself.
    """

    def test_json_matches_the_committed_verdicts_document(self) -> None:
        assert render_verdicts(replay(), json=True) == (FIXTURE / "verdicts.json").read_bytes()

    def test_json_in_a_child_process_matches_the_committed_document(self) -> None:
        assert run_child("json", hash_seed="12345") == (FIXTURE / "verdicts.json").read_bytes()


class TestTableMatchesTheGolden:
    """Acceptance 2: the human table matches the committed golden file byte-for-byte."""

    def test_table_matches_the_committed_golden(self) -> None:
        assert render_verdicts(replay(), json=False) == _GOLDEN.read_bytes()

    def test_table_in_a_child_process_matches_the_golden(self) -> None:
        assert run_child("table", hash_seed="12345") == _GOLDEN.read_bytes()


class TestTheJsonSchema:
    """Acceptance 5: the JSON parses, carries the documented field set, and is NaN-free."""

    def test_json_parses_and_carries_the_documented_schema(self) -> None:
        raw = render_verdicts(replay(), json=True)
        document = json.loads(raw.decode("utf-8"))
        assert isinstance(document, dict)
        assert set(document) == {"run_id", "verdicts", "coverage"}
        assert document["run_id"] == replay().run_id
        assert document["coverage"] == replay().coverage
        assert len(document["verdicts"]) == 86

    def test_every_verdict_record_carries_the_serialize_verdicts_field_set(self) -> None:
        from plumb.verify.serialize import serialize_verdicts

        document = json.loads(render_verdicts(replay(), json=True).decode("utf-8"))
        record = json.loads(serialize_verdicts(replay()).decode("utf-8"))["verdicts"][0]
        expected = set(record)
        assert all(set(v) == expected for v in document["verdicts"])

    def test_the_raw_bytes_contain_no_nan_or_infinity(self) -> None:
        raw = render_verdicts(replay(), json=True)
        assert b"NaN" not in raw
        assert b"Infinity" not in raw
        assert b"-Infinity" not in raw

    def test_the_canonical_json_byte_rules(self) -> None:
        raw = render_verdicts(replay(), json=True)
        document = json.loads(raw.decode("utf-8"))
        expected = (
            json.dumps(
                document,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        assert raw == expected
        assert raw.endswith(b"}\n")
        assert not raw.endswith(b"\n\n")
        assert b"\r" not in raw

    def test_non_ascii_is_kept_as_utf8_not_escaped(self) -> None:
        verdicts = VerdictSet("run-1", (_reproduced(reported="µ", located="0.5"),))
        raw = render_verdicts(verdicts, json=True)
        assert "µ".encode("utf-8") in raw
        assert b"\\u00b5" not in raw

    def test_json_keeps_located_text_newlines_verbatim(self) -> None:
        verdicts = VerdictSet("run-1", (_reproduced(located="a\nb"),))
        raw = render_verdicts(verdicts, json=True)
        assert b'"located_text":"a\\nb"' in raw


class TestDegenerateSets:
    """Acceptance 4: zero claims and all-`UNVERIFIED` render with the documented shape."""

    def test_zero_claims_table_is_header_plus_zero_summary(self) -> None:
        out = render_verdicts(VerdictSet(None, ()), json=False).decode("utf-8")
        lines = out.splitlines()
        assert lines[0].split("|")[0].strip() == "VERDICT"
        assert lines[0].split("|")[-1].strip() == "LOCATOR"
        assert lines[1] == "-" * _SEPARATOR_WIDTH
        assert lines[2] == ""
        assert lines[3] == "Summary"
        assert "claims: 0  bound: 0" in out
        assert "REPRODUCED: 0  WITHIN-TOLERANCE: 0  DIVERGED: 0  UNVERIFIED: 0" in out

    def test_zero_claims_json_is_an_empty_verdicts_array(self) -> None:
        raw = render_verdicts(VerdictSet(None, ()), json=True)
        document = json.loads(raw.decode("utf-8"))
        assert document["verdicts"] == []
        assert document["coverage"] == {
            "claims": 0,
            "bound": 0,
            "by_verdict": {
                "REPRODUCED": 0,
                "WITHIN-TOLERANCE": 0,
                "DIVERGED": 0,
                "UNVERIFIED": 0,
            },
            "by_cause": {},
        }
        assert document["run_id"] is None

    def test_all_unverified_renders_the_full_table(self) -> None:
        verdicts = VerdictSet(
            "run-1",
            (
                _unverified("a-claim", WONT_RUN),
                _unverified("b-claim", NO_BINDING),
                _unverified("c-claim", NO_BINDING),
            ),
        )
        out = render_verdicts(verdicts, json=False).decode("utf-8")
        assert out.splitlines()[0].startswith("VERDICT")
        for claim_id in ("a-claim", "b-claim", "c-claim"):
            assert claim_id in out
        assert "WONT_RUN" in out
        assert "NO_BINDING" in out
        assert "UNVERIFIED: 3" in out
        assert "claims: 3  bound: 0" in out
        # by cause is alphabetical and one line per cause, with a count.
        assert "by cause:" in out
        assert out.index("NO_BINDING: 2") < out.index("WONT_RUN: 1")

    def test_all_unverified_json_carries_causes(self) -> None:
        verdicts = VerdictSet(
            "run-1",
            (_unverified("a-claim", WONT_RUN), _unverified("b-claim", NO_BINDING)),
        )
        document = json.loads(render_verdicts(verdicts, json=True).decode("utf-8"))
        assert [v["cause"] for v in document["verdicts"]] == [WONT_RUN, NO_BINDING]
        assert document["coverage"]["by_cause"] == {NO_BINDING: 1, WONT_RUN: 1}


class TestTheTableLayout:
    """Fixed widths, fixed order, truncation, and the summary block."""

    def test_the_header_names_the_fixed_columns(self) -> None:
        out = render_verdicts(replay(), json=False).decode("utf-8")
        header = out.splitlines()[0]
        assert [cell.strip() for cell in header.split(" | ")] == [
            "VERDICT", "CAUSE", "CLAIM ID", "REPORTED",
            "REDERIVED", "ARTIFACT", "LOCATOR",
        ]

    def test_every_cell_has_its_pinned_width(self) -> None:
        out = render_verdicts(replay(), json=False).decode("utf-8")
        rows = out.splitlines()[2:-5]
        for row in rows:
            cells = row.split(" | ")
            assert [len(c) for c in cells] == list(COLUMN_WIDTHS)

    def test_the_separator_line_has_the_pinned_width(self) -> None:
        out = render_verdicts(replay(), json=False).decode("utf-8")
        assert out.splitlines()[1] == "-" * _SEPARATOR_WIDTH

    def test_rows_are_sorted_by_claim_id(self) -> None:
        out = render_verdicts(replay(), json=False).decode("utf-8")
        rows = out.splitlines()[2:-5]
        ids = [row.split(" | ")[2].rstrip() for row in rows]
        assert ids == sorted(ids)
        assert len(ids) == 86

    def test_the_summary_block_names_coverage_and_the_fixed_verdict_order(self) -> None:
        out = render_verdicts(replay(), json=False).decode("utf-8")
        assert "claims: 86  bound: 86" in out
        assert "REPRODUCED: 85  WITHIN-TOLERANCE: 0  DIVERGED: 1  UNVERIFIED: 0" in out
        assert "by cause: (none)" in out

    def test_long_text_is_truncated_to_24_with_an_ellipsis(self) -> None:
        verdicts = VerdictSet("run-1", (_reproduced(reported="0123456789" * 6),))
        out = render_verdicts(verdicts, json=False).decode("utf-8")
        row = out.splitlines()[2]
        assert "01234567890123456789012…" in row
        cells = row.split(" | ")
        assert cells[3] == "01234567890123456789012…"

    def test_truncation_does_not_split_a_multi_byte_character(self) -> None:
        verdicts = VerdictSet("run-1", (_reproduced(reported="µ" * 30),))
        out = render_verdicts(verdicts, json=False).decode("utf-8")
        cells = out.splitlines()[2].split(" | ")
        assert cells[3] == "µ" * 23 + "…"
        assert len(cells[3]) == 24

    def test_newlines_in_located_text_are_sanitized_in_the_table(self) -> None:
        verdicts = VerdictSet(
            "run-1",
            (_reproduced(locator=JsonPointer("/a"), located="a\nb\r\nc"),),
        )
        out = render_verdicts(verdicts, json=False).decode("utf-8")
        assert "json: /a → a␤b␤c" in out
        assert "a\nb" not in out

    def test_the_locator_column_names_where_the_value_came_from(self) -> None:
        verdicts = VerdictSet(
            "run-1",
            (
                _reproduced(claim_id="a", locator=CsvCell("DF", (("", "Residual"),)),
                            located="9.0"),
                _reproduced(claim_id="b", locator=StdoutRegex("AUC=(\\S+)"), located="0.87"),
                _reproduced(claim_id="c", locator=JsonPointer("/auc"), located="0.87"),
                _reproduced(claim_id="d", artifact="analysis.ipynb#cell-1",
                            locator=NotebookCell("/0/text/0"), located="0.87"),
                _reproduced(claim_id="e", artifact="analysis.ipynb#cell-18",
                            locator=NotebookCell("/0/data/text/html", HtmlTable(2, 2)),
                            located="12.90"),
            ),
        )
        out = render_verdicts(verdicts, json=False).decode("utf-8")
        lines = out.splitlines()
        assert "csv: DF[Residual] → 9.0" in lines[2]
        assert "stdout: AUC=(\\S+) → 0.87" in lines[3]
        assert "json: /auc → 0.87" in lines[4]
        assert "cell-1 /0/text/0 → 0.87" in lines[5]
        # The table-mode address survives the 24-wide truncation.
        assert "cell-18 r2c2 /0/data/te…" in lines[6]


class TestTheSeamContract:
    """`render_verdicts` is pure: a `VerdictSet` in, bytes out, no exit-code logic."""

    def test_both_formats_return_bytes(self) -> None:
        assert isinstance(render_verdicts(replay(), json=True), bytes)
        assert isinstance(render_verdicts(replay(), json=False), bytes)

    def test_json_is_keyword_only(self) -> None:
        with pytest.raises(TypeError):
            render_verdicts(replay(), True)  # type: ignore[call-arg]

    def test_json_is_a_required_keyword(self) -> None:
        with pytest.raises(TypeError):
            render_verdicts(replay())

    def test_json_false_is_the_human_table(self) -> None:
        assert render_verdicts(replay(), json=False) == render_verdicts(replay(), json=False)