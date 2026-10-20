"""Regenerate the public C5 benchmark report from the committed gate records.

The three gate records under `fixtures/gate/` are banked into a transient store, read back
through the hash-verified path, and reported with the same renderer `plumb corpus report` uses.
Nothing in the report is hand-maintained: `--check` rebuilds it and fails if the committed file
is stale, which is what CI runs.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

from plumb.cli.corpus import _render_report_table, bank_record
from plumb.corpus import read_case
from plumb.corpus.metrics import Rate, store_metrics

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "benchmark" / "REPORT.md"
AUTHORITY = "owner"

#: The panel: record directory under `fixtures/gate/`, and the paper it is.
PANEL = (
    ("agrodesign", "AgroDesign — arXiv:2603.09041 (Python/R data analysis; script entry point)"),
    ("perrin", "Perrin — arXiv:2401.11842 (R; recorded environment drift, not run-to-run "
               "stable at the paper's written precision)"),
    ("rcai", "Burtsev — arXiv:2609.00137 (Jupyter notebook; the `notebook_cell` locator)"),
)


def _rate(rate: Rate | None) -> str:
    return "no such figure" if rate is None else f"{rate.confirmed}/{rate.flagged} ({AUTHORITY})"


def build() -> str:
    """The report's exact bytes, as a str — deterministic, no clock, no machine paths."""
    with tempfile.TemporaryDirectory(prefix="plumb-benchmark-") as tmp:
        store = Path(tmp)
        banked = {
            slug: bank_record(ROOT / "fixtures" / "gate" / slug, store)[0]
            for slug, _ in PANEL
        }
        cases = [
            read_case(entry)
            for entry in sorted(store.iterdir())
            if entry.is_dir() and (entry / "case.json").is_file()
        ]
        metrics = store_metrics(cases)
        table = _render_report_table(metrics, AUTHORITY).decode("utf-8")
    totals = metrics.totals
    coverage = totals.coverage
    lines = [
        "# C5 benchmark — precision and recall over the public corpus",
        "",
        "Every figure below is regenerated from the three committed gate records, not typed by",
        "hand. Rebuild with `uv run python tools/benchmark.py`; CI runs",
        "`uv run python tools/benchmark.py --check`, which fails if this file is stale.",
        "",
        f"**Label authority: `{AUTHORITY}`.** Precision counts confirmed `DIVERGED`s over the",
        "`DIVERGED`s a human reviewed; recall counts confirmed `DIVERGED`s over every labeled",
        "claim. Labels were written by the owner (see `docs/ETHICS.md` §3); third-party labels",
        "do not exist yet.",
        "",
        "## Panel",
        "",
    ]
    lines += [f"- {line}" for _, line in PANEL]
    lines += ["", "Each row of the report is a content-addressed case id:", ""]
    lines += [f"- `{banked[slug]}` — {line.split(' — ')[0]}" for slug, line in PANEL]
    lines += [
        "",
        "## Report",
        "",
        "```",
        table.rstrip("\n"),
        "```",
        "",
        "## Refuted-verdict accounting",
        "",
        f"The panel produced **{totals.diverged} `DIVERGED`** verdicts: "
        f"**{totals.confirmed} confirmed**, **{totals.refuted} refuted** on owner review. "
        "A refuted divergence is a reproducibility finding about the artifact, not a paper "
        "error: Perrin's survival draws are unseeded, and three full runs moved every claim "
        "by more than the paper's written precision.",
        "",
        f"Coverage: **{coverage.bound}/{coverage.claims} bound** across {totals.cases} cases.",
        f"Precision: **{_rate(totals.precision)}**. Recall: **{_rate(totals.recall)}**.",
        "",
        "## What this number is not",
        "",
        "It is not a survey: three papers selected by a fixed pre-written rule, one of which is",
        "not run-to-run stable. It is not a claim about the authors. It is the honest precision",
        "of the engine on the panel it has, and it is meant to move only when the corpus grows.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the committed report is current instead of writing it")
    args = parser.parse_args(argv)
    report = build()
    if args.check:
        if not REPORT.is_file() or REPORT.read_text(encoding="utf-8") != report:
            print(f"{REPORT} is stale; run `uv run python tools/benchmark.py`", file=sys.stderr)
            return 1
        print(f"{REPORT} is current")
        return 0
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    print(REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
