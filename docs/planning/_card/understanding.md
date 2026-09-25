# Gate paper — understanding (deep dig, 2026-09-26)

## The pick

**AgroDesign: A Design-Aware Statistical Inference Framework for Agricultural Experiments in
Python** — Aqib Gul, arXiv:2603.09041v1 (10 Mar 2026), stat.ME, **CC BY 4.0**. Code:
`github.com/DeepStatistix/AgroDesign`, Apache-2.0, pure Python (pandas, numpy, scipy,
statsmodels, matplotlib, seaborn), six small CSV datasets bundled in the package. The paper
states "all statistical outputs reported in this paper correspond exactly to executable code in
the public repository". Pin: tag **v1.0.1** (`18b7c29a4f`, "Paper corrections done",
2026-02-12, before the arXiv submission); `src/` is identical to HEAD.

Why it fits: eight results tables of deterministic ANOVA / mixed-model output (MS, F, p-values,
variance components, BLUPs) plus Shapiro-Wilk p-values in the text — about 35 bindable values,
none stochastic. How the ReScience candidates failed is in `docs/planning/gate-paper/survey.md`.

## Feasibility spike (scratchpad, throwaway)

Cloned at v1.0.1, `uv pip install .` (numpy 2.5.3, pandas 3.0.6, scipy 1.18.1, statsmodels
0.15.0, matplotlib 3.11.2, seaborn 0.13.2), ran the paper's appendix workflow per design.

- The package's export writes `tables/anova_table.csv` (full-precision floats) and
  `print(result)` writes a report to stdout including Shapiro-Wilk p-values, variance
  components and BLUPs.
- Every table value checked matches the paper to its written precision (e.g. 363.333 vs
  363.3333333333342; F 5637.0 vs 5637.000000000339; p 0.262 vs 0.262143999…; BLUP 7.7 vs
  7.677…; variance 1.22 vs 1.222189).
- **One numeric discrepancy:** CRD Shapiro-Wilk — paper `0.034`, run prints `0.03455`. Any
  value in [0.034545, 0.034555) rounds to 0.035; the paper truncated. Under C4's rules
  (D1/D2) that is `DIVERGED` (review_required) — a reporting discrepancy, not misconduct.
- **One non-numeric defect:** `report_plot()` has no `return`, so with the default
  `plots=True`, `result.export(...)` raises `AttributeError: 'NoneType' object has no attribute
  'savefig'` — at v1.0.1 and at HEAD. The paper's documented workflow (`run()` then
  `export("results")`) cannot complete as written. `run(plots=False)` avoids it; figures are
  not claims.
- `mixed()` requires lists (`fixed=["Genotype"], random=["Block"]`); the paper shows no
  mixed-model code.

## C1 on this paper: 0 claims

`extract_claims(pdf_to_markdown(pdf))` admits **0** claims (290 rejections: 241
`outside_sections`, 49 `reference_numeral`). Two mechanisms:

1. The M3 selection rule does not recognise "4 Experimental Validation" as a results section.
2. The converter renders the tables as whitespace-delimited text lines
   (`Treatment 3 363.333 145.333<0.001`), not Markdown tables, so the table parser never sees
   them — and `145.333<0.001` glues two values.

This is a C1 coverage gap on the first real gate paper — R1/R3 evidence — and it must be
reported as such, not hidden behind a curated set.

## Affected areas

New: `fixtures/gate/agrodesign/` (paper PDF + provenance, claims, bindings, captured outputs,
trace, verdicts, environment freeze), `tools/gate_run.py` (the one dev-time networked run),
`tests/gate/` (offline replay). Consumes `plumb.intake` (`resolve_git`, `describe_environment`,
`build_environment`), `plumb.run` (`run_and_capture`), `plumb.verify`. Docs on landing.

## Open questions (for the PRD)

1. Claims: curated and span-grounded (C1 admits none) — acceptable for the gate, if C1's own
   number is reported next to it?
2. The driver: the repo has no entry point, so the run needs an explicit argv transcribing the
   paper's appendix workflow, with two disclosed deviations.
3. The gate asks for "a bundle a third party can replay" — C6 is not built.
4. What happens with the `DIVERGED` and the export defect (R4: right of reply).
