#!/usr/bin/env python3
"""The AgroDesign gate record's hand-written parts: claims, bindings, and the driver.

Offline, deterministic, and the single source for three committed files under
`fixtures/gate/agrodesign/`: `claims.json`, `unrepresentable.json` and `bindings.json`. The
claim set follows the rule fixed in `docs/planning/gate-paper/prd.md` (P2) — every numeric
cell of Tables 1–8 and every F / p / Shapiro-Wilk value in §4's prose — and each claim is
located by searching for its row or phrase in the normalized paper text, so a span is found,
never typed. A context that does not occur exactly once is an error.

Bindings follow from the same rows: ANOVA cells read the package's own exported
`anova_table.csv` (pandas writes shortest-repr floats, hence `float_repr`), report values read
stdout, anchored at the driver's `===== <design>` marker so each regex matches once.

`DRIVER` is the paper's appendix workflow (§A: `Experiment(...).<design>(...).run()`,
`print(result)`, `result.export(...)`) for each §4 design, with two disclosed deviations:
`run(plots=False)` — the package's `report_plot()` returns `None`, so `export()` raises with
the default at v1.0.1 and at HEAD — and list arguments to `mixed()`, which its API requires
(the paper shows no mixed-model code). Factor names are the bundled datasets' columns, as the
§4 prose names them.

Run by hand: ``uv run tools/agrodesign_spec.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.value import parse_value
from plumb.pdf import pdf_to_markdown

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "gate" / "agrodesign"

DESIGNS = ("crd", "rcbd", "factorial", "splitplot", "mixed", "gxe")

DRIVER = """\
from agrodesign.datasets import load_dataset
from agrodesign.experiment import Experiment

designs = [
    ("crd", lambda d: Experiment(d, "Yield").crd("Treatment")),
    ("rcbd", lambda d: Experiment(d, "Yield").rcbd("Variety", "Block")),
    ("factorial", lambda d: Experiment(d, "Yield").factorial(["Nitrogen", "Spacing"])),
    ("splitplot", lambda d: Experiment(d, "Yield").split_plot("Irrigation", "Variety", "Block")),
    ("mixed", lambda d: Experiment(d, "Yield").mixed(["Genotype"], ["Block"])),
    ("gxe", lambda d: Experiment(d, "Yield").gxe("Genotype", "Environment", rep="Rep")),
]
for name, build in designs:
    result = build(load_dataset(name)).run(plots=False)
    print(f"===== {name}")
    print(result)
    result.export(f"results/{name}")
"""


def anova(design: str) -> str:
    return f"results/{design}/tables/anova_table.csv"


def cell(design: str, row: str, column: str) -> tuple[str, dict, dict]:
    locator = {"kind": "csv_cell", "column": column, "row": {"": row}}
    return anova(design), locator, {"float_repr": True}


def report(design: str, pattern: str) -> tuple[str, dict, dict]:
    locator = {"kind": "stdout_regex", "pattern": rf"===== {design}\b[\s\S]*?{pattern}"}
    return "<stdout>", locator, {}


def blup(genotype: str) -> tuple[str, dict, dict]:
    locator = {"kind": "csv_cell", "column": "BLUP", "row": {"Genotype": genotype}}
    return "results/gxe/tables/blups.csv", locator, {"float_repr": True}


ANOVA_COLUMNS = ("DF", "MS", "F", "p-value")

#: (table, design, paper row label, CSV row key, the row as the paper text shows it,
#:  the columns the row fills, left to right)
ANOVA_ROWS = [
    (1, "crd", "Treatment", "C(Treatment)", "Treatment 3 363.333 145.333<0.001", 4),
    (1, "crd", "Residual", "Residual", "Residual 16 2.500 – –", 2),
    (2, "rcbd", "Variety", "C(Variety)", "Variety 3 106.667 320.000<0.001", 4),
    (2, "rcbd", "Block", "C(Block)", "Block 3 5.667 17.000<0.001", 4),
    (2, "rcbd", "Residual", "Residual", "Residual 9 0.333 – –", 2),
    (3, "factorial", "Nitrogen", "C(Nitrogen)", "Nitrogen 2 433.500 433.500<0.001", 4),
    (3, "factorial", "Spacing", "C(Spacing)", "Spacing 1 112.500 112.500<0.001", 4),
    (3, "factorial", "Nitrogen×Spacing", "C(Nitrogen):C(Spacing)",
     "Nitrogen×Spacing 2 1.500 1.500 0.262", 4),
    (3, "factorial", "Residual", "Residual", "Residual 12 1.000 – –", 2),
    (4, "splitplot", "Block", "C(Block)", "Block 2 8.111 73.0<0.001", 4),
    (4, "splitplot", "Irrigation", "C(Irrigation)", "Irrigation 2 626.333 5637.0<0.001", 4),
    (4, "splitplot", "Variety", "C(Variety)", "Variety 2 90.333 813.0<0.001", 4),
    (4, "splitplot", "Block×Irrigation", "C(Block):C(Irrigation)",
     "Block×Irrigation 4 0.111 1.0 0.445", 4),
    (4, "splitplot", "Irrigation×Variety", "C(Irrigation):C(Variety)",
     "Irrigation×Variety 4 1.333 12.0<0.001", 4),
    (4, "splitplot", "Residual", "Residual", "Residual 12 0.111 – –", 2),
    (7, "gxe", "Genotype", "C(Genotype)", "Genotype 3 364.458 728.917<0.001", 4),
    (7, "gxe", "Environment", "C(Environment)", "Environment 3 42.458 84.917<0.001", 4),
    (7, "gxe", "Genotype×Environment", "C(Genotype):C(Environment)",
     "Genotype×Environment 9 0.458 0.917 0.535", 4),
    (7, "gxe", "Residual", "Residual", "Residual 16 0.500 – –", 2),
]

#: (table, metric, context in the paper, value text, binding)
OTHER_TABLE_CELLS = [
    (5, "mixed variance component Block", "Block (random) 1.22", "1.22",
     report("mixed", r"Block \(random\)\s+(\S+)")),
    (5, "mixed variance component Residual", "Residual (random) 0.44", "0.44",
     report("mixed", r"Residual \(random\)\s+(\S+)")),
    (6, "mixed BLUP T3", "T3 54.5", "54.5", report("mixed", r"\nT3\s+(\S+)")),
    (6, "mixed BLUP T2", "T2 48.5", "48.5", report("mixed", r"\nT2\s+(\S+)")),
    (6, "mixed BLUP T1", "T1 41.5", "41.5", report("mixed", r"\nT1\s+(\S+)")),
    (8, "gxe BLUP G4", "G4 7.7", "7.7", blup("G4")),
    (8, "gxe BLUP G3", "G3 2.7", "2.7", blup("G3")),
    (8, "gxe BLUP G2", "G2 -2.3", "-2.3", blup("G2")),
    (8, "gxe BLUP G1", "G1 -8.1", "-8.1", blup("G1")),
]

_SHAPIRO = r"Shapiro-Wilk normality test: p = (\S+)"

#: (section, metric, context in the paper, value text, binding)
PROSE = [
    ("4.1", "CRD Treatment F (prose)", "(F = 145.33, p ¡ 0.001)", "145.33",
     cell("crd", "C(Treatment)", "F")),
    ("4.1", "CRD Shapiro-Wilk p (prose)", "(p-value = 0.034)", "0.034", report("crd", _SHAPIRO)),
    ("4.2", "RCBD Variety F (prose)", "(F = 320.00, p ¡ 0.001)", "320.00",
     cell("rcbd", "C(Variety)", "F")),
    ("4.2", "RCBD Shapiro-Wilk p (prose)", "(Shapiro-Wilk test p-value = 0.064)", "0.064",
     report("rcbd", _SHAPIRO)),
    ("4.3", "factorial interaction F (prose)", "(F = 1.50, p = 0.262)", "1.50",
     cell("factorial", "C(Nitrogen):C(Spacing)", "F")),
    ("4.3", "factorial interaction p (prose)", "(F = 1.50, p = 0.262)", "0.262",
     cell("factorial", "C(Nitrogen):C(Spacing)", "p-value")),
    ("4.3", "factorial Shapiro-Wilk p (prose)", "p-value = 0.0016)", "0.0016",
     report("factorial", _SHAPIRO)),
    ("4.4", "split-plot Irrigation×Variety F (prose)", "(F= 12.0, p <0.001)", "12.0",
     cell("splitplot", "C(Irrigation):C(Variety)", "F")),
    ("4.4", "split-plot Irrigation×Variety p (prose)", "(F= 12.0, p <0.001)", "p <0.001",
     cell("splitplot", "C(Irrigation):C(Variety)", "p-value")),
    ("4.6", "G×E interaction p (prose)", "(p = 0.535)", "0.535",
     cell("gxe", "C(Genotype):C(Environment)", "p-value")),
    ("4.6", "G×E Shapiro-Wilk p (prose)", "(p = 0.121)", "0.121", report("gxe", _SHAPIRO)),
]

#: Members of the rule that cannot be a `Claim`: the PDF's own text.
UNREPRESENTABLE = [
    ("4.1", "(F = 145.33, p ¡ 0.001)", "p ¡ 0.001"),
    ("4.2", "(F = 320.00, p ¡ 0.001)", "p ¡ 0.001"),
]
_GLYPH = (
    "the PDF renders `<` as `¡` (a LaTeX text-mode `<` in the OT1 encoding), so the paper's "
    "own text is not a parseable bound"
)


def unique_offset(text: str, context: str) -> int:
    first = text.find(context)
    if first < 0 or text.find(context, first + 1) >= 0:
        raise ValueError(f"context must occur exactly once in the paper: {context!r}")
    return first


def build(paper_text: str) -> tuple[list[dict], list[dict], list[dict]]:
    """The claim entries, the unrepresentable entries, and the binding entries."""
    claims: list[dict] = []
    bindings: list[dict] = []

    def add(text, metric, source, context, start, target):
        entry = {"text": text, "metric": metric, "source": source, "context": context,
                 "start": start, "end": start + len(text)}
        claim = Claim(parse_value(text), None, metric, CharSpan(start, start + len(text)),
                      None, None)
        artifact, locator, extra = target
        claims.append(entry)
        bindings.append({"claim_id": claim.id, "artifact": artifact, "locator": locator, **extra})

    for table, design, label, key, row_text, filled in ANOVA_ROWS:
        base = unique_offset(paper_text, row_text)
        cursor = len(label)
        for column, value in zip(ANOVA_COLUMNS[:filled], row_text[len(label):].replace("<", " <").split()):
            at = row_text.index(value, cursor)
            cursor = at + len(value)
            metric = f"Table {table} {design} ANOVA {label} {column}"
            add(value, metric, "table", row_text, base + at, cell(design, key, column))

    for table, metric, context, value, target in OTHER_TABLE_CELLS:
        base = unique_offset(paper_text, context)
        add(value, f"Table {table} {metric}", "table", context,
            base + context.index(value), target)

    for section, metric, context, value, target in PROSE:
        base = unique_offset(paper_text, context)
        add(value, f"§{section} {metric}", "prose", context, base + context.index(value), target)

    unrepresentable = []
    for section, context, value in UNREPRESENTABLE:
        start = unique_offset(paper_text, context) + context.index(value)
        unrepresentable.append({"section": section, "text": value, "context": context,
                                "start": start, "end": start + len(value), "reason": _GLYPH})
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
    print(f"{len(claims)} claims, {len(unrepresentable)} unrepresentable, {len(bindings)} bindings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
