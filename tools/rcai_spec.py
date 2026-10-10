#!/usr/bin/env python3
"""The RCAI gate fixture's claims and bindings: rule-encoded, fixed before any run.

Offline, deterministic, and the single source for `fixtures/gate/rcai/claims.json` and
`fixtures/gate/rcai/bindings.json`. The claim set follows the rule fixed in
`docs/planning/notebook-paper/prd.md` (P2) and recorded verbatim in the fixture README:
every numeric cell of Table 1 (the four reference scenarios and the no-RSI baseline) and
Table 2 (the three strategic-market regimes), plus the unqualified numeric statistics
stated in the results prose (§3.3 and §4.1). Each claim is located by searching for its
row or phrase in the normalized paper text, so a span is found, never typed; a context
that does not occur exactly once is an error.

Statistics the prose qualifies with an approximation marker (`about`, `approximately`,
`≃`) are excluded from the rule: the paper declines to state a precise value, so no
written-precision reading exists. The exclusions are listed in the fixture README.

The bindings half (P3, committed BEFORE the notebook is ever run) aims the claim set at the
paper's own notebook outputs: the two pandas Styler tables are the `display_data` outputs
of cells-array indices 18 and 28, whose values live only in the `text/html` leaf, so every
locator is `notebook_cell` table mode (N1) on
`Recursive_Criticality_of_AI_Self_Improvement.ipynb#cell-18|#cell-28` at pointer
`/0/data/text/html`. The grid geometry is the table's row order (grid column 0 is the
row's scenario/configuration name; a `<th>`-only header row is not a grid row) and the
numeric columns left to right. The declared reading is the written-precision band for
every binding — both Stylers write fixed-format roundings (`a` as `{:.1f}`, the rest
`{:.2f}`; cell 28 `precision=2`), so no binding carries `float_repr`. §4.1's
`KAA = 1.00` statistic has no cell among the two Styler outputs and stays unbound, an
expected `NO_BINDING`. The reference notebook is dev-time evidence only (fetched to a path
outside the repo; URL and SHA-256 in the fixture README), never executed by this generator.

Run by hand: ``uv run tools/rcai_spec.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.value import parse_value
from plumb.pdf import pdf_to_markdown

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gate" / "rcai"

#: Table 1's numeric columns, left to right (the scenario column is its row's name).
TABLE_1_COLUMNS = (
    "recursive gain a", "AGI crossing T_AGI", "ASI crossing T_ASI", "AGI-to-ASI interval ΔT",
)
TABLE_2_COLUMNS = ("AGI crossing T_AGI", "ASI crossing T_ASI", "AGI-to-ASI interval ΔT")

#: (scenario, the row as the paper text shows it) — all rows, every numeric cell.
TABLE_1_ROWS = [
    ("No-RSI baseline", "No-RSI baseline 0 24.00 96.00 72.00"),
    ("Smooth scaling", "Smooth scaling 0.5 21.35 74.13 52.79"),
    ("Weak supercriticality", "Weak supercriticality 3 12.90 24.73 11.83"),
    ("Transient takeoff", "Transient takeoff 6 8.40 11.08 2.69"),
    ("Rapid AGI-to-ASI", "Rapid AGI-to-ASI 15 4.50 4.95 0.45"),
]
TABLE_2_ROWS = [
    ("Closed frontier-lab competition", "Closed frontier-lab competition 10.40 16.53 6.13"),
    ("Open competitive ecosystem", "Open competitive ecosystem 9.75 12.58 2.82"),
    ("Global competition", "Global competition 8.97 13.42 4.45"),
]

#: The notebook and the pointer to the Styler leaf inside each cell's one output (its
#: `text/plain` is a nondeterministic `Style at 0x…` repr; the values are in `text/html`).
NOTEBOOK = "Recursive_Criticality_of_AI_Self_Improvement.ipynb"
STYLER_POINTER = "/0/data/text/html"
TABLE_1_CELL = 18
TABLE_2_CELL = 28

#: (section, metric, context in the paper, value text, grid target or None) — the
#: unqualified results statistics. §3.3's `72` is the interval Table 1's no-RSI baseline
#: row displays (`(row, column)` = (0, 4)); §4.1's `KAA = 1.00` is computed in cell 23,
#: outside the two pre-registered Styler cells, so it stays unbound.
PROSE = [
    ("3.3", "no-RSI AGI-to-ASI interval (prose)",
     "compressing the AGI-to-ASI interval from72 years", "72",
     (TABLE_1_CELL, 0, len(TABLE_1_COLUMNS))),
    ("4.1", "closed laboratory leading actor reproduction number K_AA (prose)",
     "the local critical boundary, KAA = 1.00", "1.00", None),
]


def unique_offset(text: str, context: str) -> int:
    first = text.find(context)
    if first < 0 or text.find(context, first + 1) >= 0:
        raise ValueError(f"context must occur exactly once in the paper: {context!r}")
    return first


def build(paper_text: str) -> tuple[list[dict], list[dict]]:
    """The claim entries and the binding entries, both in rule order."""
    entries: list[dict] = []
    bindings: list[dict] = []

    def add(text: str, metric: str, source: str, context: str, start: int,
            target: tuple[int, int, int] | None) -> None:
        claim = Claim(parse_value(text), None, metric,
                      CharSpan(start, start + len(text)), None, None)
        entries.append({"text": text, "metric": metric, "source": source, "context": context,
                        "start": start, "end": start + len(text)})
        if target is None:
            return
        cell, row, column = target
        bindings.append({
            "claim_id": claim.id,
            "artifact": f"{NOTEBOOK}#cell-{cell}",
            "locator": {"kind": "notebook_cell", "pointer": STYLER_POINTER,
                        "table": {"row": row, "column": column}},
        })

    for table, cell, rows, columns in ((1, TABLE_1_CELL, TABLE_1_ROWS, TABLE_1_COLUMNS),
                                       (2, TABLE_2_CELL, TABLE_2_ROWS, TABLE_2_COLUMNS)):
        for index, (scenario, row_text) in enumerate(rows):
            base = unique_offset(paper_text, row_text)
            cursor = len(scenario)
            values = zip(range(1, len(columns) + 1), columns, row_text[len(scenario):].split())
            for column, name, value in values:
                at = row_text.index(value, cursor)
                cursor = at + len(value)
                add(value, f"Table {table} {scenario} {name}", "table", row_text,
                    base + at, (cell, index, column))

    for section, metric, context, value, target in PROSE:
        base = unique_offset(paper_text, context)
        add(value, f"§{section} {metric}", "prose", context, base + context.index(value),
            target)

    return entries, bindings


def claims_for(entries: list[dict]) -> list[Claim]:
    return [
        Claim(parse_value(entry["text"]), None, entry["metric"],
              CharSpan(entry["start"], entry["end"]), None, None)
        for entry in entries
    ]


def main() -> int:
    paper = normalize_text(pdf_to_markdown((FIXTURE / "paper.pdf").read_bytes()))
    entries, bindings = build(paper)
    claims = claims_for(entries)
    ids = {claim.id for claim in claims}
    if len(ids) != len(claims):
        raise ValueError("the rule produced two claims sharing an id")
    if len({binding["claim_id"] for binding in bindings}) != len(bindings):
        raise ValueError("the rule bound one claim twice")
    (FIXTURE / "claims.json").write_text(
        json.dumps({"claims": entries}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    bindings.sort(key=lambda binding: binding["claim_id"])
    (FIXTURE / "bindings.json").write_text(
        json.dumps({"bindings": bindings}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"{len(entries)} claims, {len(ids)} distinct ids, {len(bindings)} bindings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
