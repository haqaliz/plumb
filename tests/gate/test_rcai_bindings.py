"""The RCAI gate fixture: the pre-registered bindings, committed before any run (P3/P4).

`bindings.json` aims each claim at its notebook cell output through `notebook_cell`
locators, before the notebook is ever executed (anti-inflation: the enumeration and the
(row, column) addresses are fixed here; no claim may be added or re-aimed after seeing a
verdict). The two Styler tables are the `display_data` outputs of cells-array indices 18
and 28 of the paper's own notebook — fetched at dev time (2026-10-10) from
`https://raw.githubusercontent.com/burtsev/recursive-criticality-ai/main/Recursive_Criticality_of_AI_Self_Improvement.ipynb`
(SHA-256 `17b3a0c5d407afa52d3ca49956324553a4d0cfba6b69103b6f8ba73f37b07fab`) to a path
outside the repo, **never committed, never executed** by tests or CI. Their values live
only in `text/html` (the `text/plain` leaf is a nondeterministic `Style at 0x…` repr), so
every locator is table mode (N1).

The grids below are the reference notebook's stored outputs as the N1 grammar reads them:
one grid row per `<tr>` carrying `<td>`s — a `<th>`-only header row does **not** consume a
grid row — grid column 0 the row's scenario/configuration name, then the numeric columns
left to right. The bindings file carries the claim ids in sorted order; the declared
reading is the written-precision band for every binding (`float_repr` absent — both Stylers
write fixed-format roundings: `a` as `{:.1f}`, the rest `{:.2f}`; cell 28 `precision=2`).
One prose claim — §4.1's `KAA = 1.00` — has no cell among the two pre-registered Styler
outputs and stays unbound, an expected `NO_BINDING`.
"""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan
from plumb.extract.value import parse_value
from plumb.verify.bindings import NotebookCell, load_bindings

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gate" / "rcai"

NOTEBOOK = "Recursive_Criticality_of_AI_Self_Improvement.ipynb"
STYLER_CELLS = (18, 28)
STYLER_POINTER = "/0/data/text/html"

REFERENCE_URL = (
    "https://raw.githubusercontent.com/burtsev/recursive-criticality-ai/main/"
    "Recursive_Criticality_of_AI_Self_Improvement.ipynb"
)
REFERENCE_SHA256 = "17b3a0c5d407afa52d3ca49956324553a4d0cfba6b69103b6f8ba73f37b07fab"

#: Table 1 — cell 18: (scenario, a, T_AGI, T_ASI, ΔT) per grid row; header `a` `{:.1f}`,
#: the rest `{:.2f}`. Grid column 0 is the scenario name (the row-heading `<th>` is not a
#: `<td>` and the header row carries no `<td>`, so neither consumes a grid position).
TABLE_1_GRID = (
    ("No-RSI baseline", "0.0", "24.00", "96.00", "72.00"),
    ("Smooth scaling", "0.5", "21.35", "74.13", "52.79"),
    ("Weak supercriticality", "3.0", "12.90", "24.73", "11.83"),
    ("Transient takeoff", "6.0", "8.40", "11.08", "2.69"),
    ("Rapid AGI-to-ASI", "15.0", "4.50", "4.95", "0.45"),
)
#: Table 2 — cell 28: (configuration, T_AGI, T_ASI, ΔT); `precision=2`.
TABLE_2_GRID = (
    ("Closed frontier-lab competition", "10.40", "16.53", "6.13"),
    ("Open competitive ecosystem", "9.75", "12.58", "2.82"),
    ("Global competition", "8.97", "13.42", "4.45"),
)
TABLES = {"Table 1": (18, TABLE_1_GRID), "Table 2": (28, TABLE_2_GRID)}

#: The only places the paper's written digits differ from the cell's fixed-format
#: rendering: the Styler writes `a` with `{:.1f}` and prose-`72` is Table 1's `72.00`.
FORMAT_VARIANTS = {
    ("0", "0.0"), ("3", "3.0"), ("6", "6.0"), ("15", "15.0"), ("72", "72.00"),
}

PROSE_72 = "§3.3 no-RSI AGI-to-ASI interval (prose)"
UNBOUND_METRICS = frozenset({
    "§4.1 closed laboratory leading actor reproduction number K_AA (prose)",
})


def load_claims() -> list[Claim]:
    entries = json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))["claims"]
    return [
        Claim(parse_value(e["text"]), None, e["metric"], CharSpan(e["start"], e["end"]),
              None, None)
        for e in entries
    ]


def binding_entries() -> list[dict]:
    document = json.loads((FIXTURE / "bindings.json").read_text(encoding="utf-8"))
    return document["bindings"]


def binding_for(claim_id: str) -> dict:
    entries = [e for e in binding_entries() if e["claim_id"] == claim_id]
    assert len(entries) == 1, claim_id
    return entries[0]


def test_every_claim_is_bound_exactly_once_except_the_documented_unbound() -> None:
    claims = load_claims()
    ids = [c.id for c in claims]
    bound = [e["claim_id"] for e in binding_entries()]
    assert len(bound) == len(set(bound)), "a claim is bound more than once"
    assert set(bound) <= set(ids), "a binding names no input claim"
    by_id = {c.id: c for c in claims}
    unbound = [by_id[i] for i in set(ids) - set(bound)]
    assert {c.metric for c in unbound} == UNBOUND_METRICS


def test_the_file_is_sorted_by_claim_id_and_loads_as_bindings() -> None:
    raw = (FIXTURE / "bindings.json").read_bytes()
    ids = [e["claim_id"] for e in binding_entries()]
    assert ids == sorted(ids)
    loaded = load_bindings(raw, [c.id for c in load_claims()])
    assert [b.claim_id for b in loaded.values()] == ids
    assert all(b.invalid is None for b in loaded.values())
    assert all(isinstance(b.locator, NotebookCell) and b.locator.table is not None
               for b in loaded.values())


def test_every_locator_targets_one_of_the_two_styler_cells() -> None:
    artifacts = {f"{NOTEBOOK}#cell-{i}" for i in STYLER_CELLS}
    for entry in binding_entries():
        assert entry["artifact"] in artifacts, entry
        locator = entry["locator"]
        assert locator["kind"] == "notebook_cell", entry
        assert locator["pointer"] == STYLER_POINTER, entry
        assert set(locator) == {"kind", "pointer", "table"}, entry
        assert set(locator["table"]) == {"row", "column"}, entry
        assert all(type(v) is int and v >= 0 for v in locator["table"].values()), entry


def test_no_binding_declares_float_repr() -> None:
    raw = (FIXTURE / "bindings.json").read_bytes()
    assert "float_repr" not in raw.decode("utf-8")
    loaded = load_bindings(raw, [c.id for c in load_claims()])
    assert all(b.float_repr is False for b in loaded.values())


def test_table_bindings_address_the_claim_value_in_the_reference_grid() -> None:
    for claim in load_claims():
        table = next((t for t in TABLES if claim.metric.startswith(f"{t} ")), None)
        if table is None:
            continue
        cell, grid = TABLES[table]
        entry = binding_for(claim.id)
        assert entry["artifact"] == f"{NOTEBOOK}#cell-{cell}", claim.metric
        row, column = entry["locator"]["table"]["row"], entry["locator"]["table"]["column"]
        remainder = claim.metric[len(f"{table} "):]
        scenario = next(s for s in (r[0] for r in grid) if remainder.startswith(s + " "))
        assert grid[row][0] == scenario, claim.metric
        assert row == [r[0] for r in grid].index(scenario), claim.metric
        text = grid[row][column]
        assert Decimal(text) == Decimal(claim.reported_value.text), claim.metric
        written = claim.reported_value.text
        assert written == text or (written, text) in FORMAT_VARIANTS, claim.metric


def test_the_table_grids_carry_no_repeated_value() -> None:
    for table, (_, grid) in TABLES.items():
        values = [v for row in grid for v in row[1:]]
        assert len(values) == len(set(Decimal(v) for v in values)), table


def test_the_prose_statistic_binds_table_1s_no_rsi_interval() -> None:
    claim = next(c for c in load_claims() if c.metric == PROSE_72)
    entry = binding_for(claim.id)
    assert entry["artifact"] == f"{NOTEBOOK}#cell-18"
    assert entry["locator"]["table"] == {"row": 0, "column": 4}
    assert TABLE_1_GRID[0][4] == "72.00"
    assert Decimal(TABLE_1_GRID[0][4]) == Decimal(claim.reported_value.text)


def test_the_fetch_and_the_unbound_claim_are_recorded_in_the_readme() -> None:
    readme = " ".join((FIXTURE / "README.md").read_text(encoding="utf-8").split())
    assert REFERENCE_URL in readme
    assert REFERENCE_SHA256 in readme
    assert "never executed" in readme
    assert "cell-18" in readme and "cell-28" in readme
    assert "NO_BINDING" in readme
    assert "written-precision band" in readme
    for metric in UNBOUND_METRICS:
        assert metric in readme
