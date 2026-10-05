#!/usr/bin/env python3
"""The Perrin et al. gate record's hand-written parts: claims, bindings, and the driver.

Offline, deterministic, and the single source for three committed files under
`fixtures/gate/perrin/`: `claims.json`, `unrepresentable.json` and `bindings.json`. The
claim set follows the rule fixed in the fixture README (written before any run or
binding): every numeric performance cell of the paper's main-text results tables
(Table 1 type I error, §6.1; Tables 2–4 semi-synthetic, §6.4). Each member is located by
searching for its full row in the normalized paper text — a span is found, never typed —
and each cell sits at its offset within that row. A context that does not occur exactly
once is an error.

Members become claims only where the scenario re-derives within the panel's dev-time
budget (probe measurements in the README): Table 1's p=20 and p=100 columns (16 cells).
The other 217 members (Table 1 p=1000; Tables 2–4) are recorded in `unrepresentable.json`
with the measured runtime reason — they parse fine; their scenarios are cluster-scale.

Bindings read the driver's reduced tables: the mean of `thresh_pval` per method over the
1000 repetitions of the fresh processed CSV, exactly the analysis notebook's reduction
(`analysis_rq1.py`, "Type I error (main paper)" cell, scale=1.0). pandas writes
shortest-repr floats, hence `float_repr`.

`DRIVER` transcribes the paper's type-I-error workflow (§6.1 Table 1 caption): for each
dimension, `power_analysis` at the single ARR=0 point with 1000 repetitions, sample size
500, 0.5/0.5 split, first censoring scenario, the same method sets Table 1 reports
(p=20: all 9 incl. SIDES/SeqBT; p=100: 7 — the paper's "–" cells). Two disclosed
deviations: the run changes into `hte/experiments` (the package's own workflow requires
it — `run_experiments.py` imports `analyze_expe` from the cwd), and the pipeline names
its CSVs with a wall-clock timestamp, so the driver copies each fresh CSV's reduction to
a canonical name for binding (bytes untouched).

Run by hand: ``uv run tools/perrin_spec.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.value import parse_value
from plumb.pdf import pdf_to_markdown

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gate" / "perrin"

#: Table 1 rows as the paper prints them: (row text, pipeline `method`, paper label).
#: The pipeline's method names differ from the paper's labels for four rows.
TYPE1_ROWS = [
    ("Univariate interaction 0.028 0.007 0.001", "Univariate interaction", "Univariate interaction"),
    ("Univariate t-test 0.035 0.052 0.052", "Univariate t_test", "Univariate t-test"),
    ("Multivariate Cox 0.042 0.033 0.037", "Multivariate cox", "Multivariate Cox"),
    ("Multivariate Tree 0.051 0.051 0.051", "Multivariate tree", "Multivariate Tree"),
    ("MOB 0.060 0.043 0.056", "MOB", "MOB"),
    ("IT 0.024 0.011 0.002", "ITree", "IT"),
    ("ARDP 0.036 0.049 0.043", "ARDP", "ARDP"),
    ("SIDES 0.125 – –", "SIDES", "SIDES"),
    ("SeqBT 0.042 – –", "SeqBT", "SeqBT"),
]

#: Tables 2–4 rows as the paper prints them: (row text, table column labels in the
#: paper's own order, the row's ARR token). The PDF converter merged the "MOB ITree"
#: header into one token; the row values still come in the paper's column order.
SEMI_SYNTH_ROWS = [
    ("0.00 0.07 0.00 0.03 0.03 0.05 0.03 0.00 0.02", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.04 0.09 0.00 0.04 0.03 0.04 0.04 0.00 0.07", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.08 0.32 0.00 0.05 0.05 0.12 0.04 0.00 0.06", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.13 0.64 0.04 0.08 0.06 0.07 0.06 0.04 0.04", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.17 0.94 0.07 0.05 0.05 0.03 0.08 0.13 0.01", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.21 1.00 0.23 0.09 0.04 0.01 0.14 0.24 0.08", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.25 1.00 0.51 0.09 0.13 0.04 0.29 0.55 0.07", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.29 1.00 0.80 0.12 0.22 0.08 0.35 0.90 0.09", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.34 1.00 0.96 0.18 0.43 0.04 0.71 0.98 0.10", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.38 1.00 1.00 0.42 0.69 0.12 0.95 1.00 0.18", "Table 2", "power",
     ["Oracle", "U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.00 0.01 0.01 0.01 0.01 0.01 0.04", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.04 0.01 0.01 0.01 0.01 0.02 0.04", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.08 0.02 0.01 0.01 0.01 0.02 0.03", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.13 0.04 0.02 0.01 0.02 0.02 0.04", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.17 0.07 0.03 0.02 0.03 0.05 0.04", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.21 0.09 0.03 0.01 0.03 0.04 0.04", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.25 0.11 0.04 0.03 0.04 0.04 0.04", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.29 0.13 0.04 0.03 0.05 0.07 0.05", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.34 0.13 0.05 0.03 0.08 0.12 0.05", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.38 0.14 0.04 0.05 0.11 0.17 0.04", "Table 3", "averaged precision",
     ["U interaction", "U t-test", "M Cox", "MOB", "ITree", "ARDP"]),
    ("0.00 0.52 0.51 0.50 0.49 0.51 0.51 0.53", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.04 0.52 0.52 0.52 0.49 0.51 0.51 0.54", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.08 0.52 0.51 0.54 0.49 0.51 0.51 0.52", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.13 0.54 0.52 0.57 0.49 0.51 0.51 0.53", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.17 0.57 0.53 0.58 0.49 0.51 0.53 0.54", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.21 0.57 0.53 0.59 0.49 0.51 0.57 0.55", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.25 0.57 0.53 0.63 0.49 0.53 0.64 0.56", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.29 0.59 0.53 0.63 0.49 0.54 0.73 0.56", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.34 0.58 0.54 0.66 0.49 0.57 0.79 0.55", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
    ("0.38 0.58 0.54 0.69 0.52 0.57 0.82 0.56", "Table 4", "accuracy",
     ["U interaction", "U t-test", "M Cox", "M Tree", "MOB", "ITree", "ARDP"]),
]

#: The measured reason every out-of-budget member carries (probe, 2026-10-03).
OUT_OF_BUDGET_REASON = (
    "cannot be re-derived within the panel's laptop-CPU budget: ARDP's p=1000 fit alone "
    "measures ~15.5 min per repetition (930 s), so the p=1000 type-I-error scenario (1000 "
    "repetitions) is ~24 CPU-hours and the semi-synthetic scenario (100 repetitions x 10 "
    "ARR points at p=1000) is ~21 CPU-hours on this 14-core machine; recorded, not forced "
    "(panel-run screening.md section 4, plan_20261002.md)"
)

DRIVER = """\
import glob
import json
import os
import numpy as np
import pandas as pd

os.chdir("hte/experiments")
from hte.experiments.launch_expe import find_upper_bound
from hte.experiments.run_experiments import power_analysis

os.makedirs("results_expe/raw_results", exist_ok=True)
os.makedirs("results_expe/processed_results", exist_ok=True)
os.makedirs("results_expe/reduced", exist_ok=True)

GRIDS = {
    "p20": "../data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=20_range=[-10.0,10.0]_nb=500_group=[dim20_pred4_prog0_balanced]_July_07_12_2023_15:15:24.json",
    "p100": "../data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=100_range=[-10.0,10.0]_nb=500_group=[dim100_pred4_prog0_balanced]_July_07_25_2023_16:08:59.json",
}
METHODS = {
    "p20": "Oracle, Univariate interaction, Univariate t_test, Multivariate cox, Multivariate tree, MOB, ITree, SIDES, SeqBT, ARDP",
    "p100": "Oracle, Univariate interaction, Univariate t_test, Multivariate cox, Multivariate tree, MOB, ITree, ARDP",
}

for name in ("p20", "p100"):
    dim = name[1:]
    with open(GRIDS[name]) as f:
        dict_param = json.load(f)
    upper, _ = find_upper_bound(dict_param)
    np.random.seed(seed=42)
    power_analysis(
        arrs=np.linspace(0.0, float(upper), 1),
        dict_param_path=GRIDS[name], train_size=250, test_size=250,
        repet=1000, censored=True, scale=1.0, semi_synth=False,
        methods=METHODS[name])
    fresh = glob.glob("results_expe/processed_results/*dim={}_range=*scale=1.0*.csv".format(dim))
    if len(fresh) != 1:
        raise SystemExit("expected one fresh processed CSV for p{}, found {}".format(dim, fresh))
    df = pd.read_csv(fresh[0], index_col=0)
    reduced = df.groupby("method")["thresh_pval"].mean().reset_index()
    reduced.to_csv("results_expe/reduced/type1_{}.csv".format(name), index=False)
    os.remove(fresh[0])
    for leftover in glob.glob("results_expe/raw_results/*"):
        os.remove(leftover)
    print("===== {}".format(name))
    print(reduced.to_string(index=False))
"""


def unique_offset(text: str, context: str) -> int:
    first = text.find(context)
    if first < 0 or text.find(context, first + 1) >= 0:
        raise ValueError(f"context must occur exactly once in the paper: {context!r}")
    return first


def cells(row: str, label_len: int, skip: set[str]) -> list[tuple[str, int]]:
    """The (value, offset-in-row) cells of `row` after the label; `skip` tokens (the
    paper's "–") are not cells."""
    found = []
    cursor = label_len
    for token in row[label_len:].split():
        at = row.index(token, cursor)
        cursor = at + len(token)
        if token not in skip:
            found.append((token, at))
    return found


def build(paper_text: str) -> tuple[list[dict], list[dict], list[dict]]:
    """The claim entries, the unrepresentable entries, and the binding entries."""
    claims: list[dict] = []
    bindings: list[dict] = []
    unrepresentable: list[dict] = []

    def add_claim(text, metric, context, start, artifact, method):
        entry = {"text": text, "metric": metric, "source": "table", "context": context,
                 "start": start, "end": start + len(text)}
        claim = Claim(parse_value(text), None, metric, CharSpan(start, start + len(text)),
                      None, None)
        claims.append(entry)
        bindings.append({"claim_id": claim.id, "artifact": artifact,
                         "locator": {"kind": "csv_cell", "column": "thresh_pval",
                                     "row": {"method": method}},
                         "float_repr": True})

    def add_unrepresentable(text, metric, context, start, reason):
        unrepresentable.append({"section": metric, "text": text, "context": context,
                                "start": start, "end": start + len(text), "reason": reason})

    for row, method, label in TYPE1_ROWS:
        base = unique_offset(paper_text, row)
        values = cells(row, len(label), skip={"–"})
        # values: [p=20, p=100, p=1000] where the row reports them.
        for column, (value, at) in enumerate(values):
            metric = f"Table 1 {label} type I error p={('20', '100', '1000')[column]}"
            if column in (0, 1):  # the scenarios this machine can re-derive
                add_claim(value, metric, row, base + at,
                          f"hte/experiments/results_expe/reduced/type1_p{('20', '100')[column]}.csv",
                          method)
            else:  # p=1000: cluster-scale, recorded with the measured reason
                add_unrepresentable(value, metric, row, base + at, OUT_OF_BUDGET_REASON)

    for row, table, what, columns in SEMI_SYNTH_ROWS:
        base = unique_offset(paper_text, row)
        arr = row.split()[0]
        for (value, at), column in zip(cells(row, len(arr), skip=set()), columns):
            metric = f"{table} {column} {what} at ARR {arr}"
            add_unrepresentable(value, metric, row, base + at, OUT_OF_BUDGET_REASON)

    return claims, unrepresentable, bindings


def main() -> int:
    paper = normalize_text(pdf_to_markdown((FIXTURE / "paper.pdf").read_bytes()))
    claims, unrepresentable, bindings = build(paper)
    for name, key, rows in (("claims.json", "claims", claims),
                            ("unrepresentable.json", "unrepresentable", unrepresentable),
                            ("bindings.json", "bindings", bindings)):
        (FIXTURE / name).write_text(
            json.dumps({key: rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    print(f"{len(claims)} claims, {len(unrepresentable)} unrepresentable, "
          f"{len(bindings)} bindings")
    return 0


if __name__ == "__main__":
    sys.exit(main())