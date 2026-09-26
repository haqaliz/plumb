# Gate fixture: AgroDesign (arXiv:2603.09041)

The first real paper run through Plumb's spine (C2 intake → C3 run → C4 bind & verdict), for
the Phase 0 gate. Planning: `docs/planning/gate-paper/` (the survey, PRD and plan).

## Provenance

| | |
|---|---|
| Paper | Aqib Gul, *AgroDesign: A Design-Aware Statistical Inference Framework for Agricultural Experiments in Python*, arXiv:2603.09041v1 [stat.ME], 10 March 2026 |
| Paper licence | [CC BY 4.0](http://creativecommons.org/licenses/by/4.0/) — `paper.pdf` is redistributed unmodified, with attribution |
| Paper source | `https://arxiv.org/pdf/2603.09041v1`, fetched 2026-09-25 (owner-authorized dev-time fetch) |
| `paper.pdf` SHA-256 | `c2dea137e795ba9f9acc432647d4df3f88b95a3a9c9f5dacfc5c9af8a1abead7` |
| Code | `https://github.com/DeepStatistix/AgroDesign`, Apache-2.0 — **not vendored**; resolved at run time by `tools/gate_run.py` |
| Pinned rev | tag `v1.0.1` = `18b7c29a4f…` ("Paper corrections done", 2026-02-12 — the last code change before the arXiv submission; `src/` is identical to HEAD) |
| Data | the six CSV datasets bundled in the package (`src/agrodesign/datasets/data/`) — synthetic, per the paper's §7 |

## Files

| File | What it is | Written by |
|---|---|---|
| `paper.pdf` | the paper | fetched once |
| `claims.json` | the rule-defined claim set, each claim at its verbatim span in `normalize_text(pdf_to_markdown(paper.pdf))` | `tools/agrodesign_spec.py` |
| `unrepresentable.json` | members of the rule that cannot be a `Claim`, with the reason | `tools/agrodesign_spec.py` |
| `bindings.json` | one binding per claim | `tools/agrodesign_spec.py` |

**The claim rule** (fixed before binding, `docs/planning/gate-paper/prd.md` P2): every numeric
cell of Tables 1–8, and every F, p and Shapiro-Wilk value stated in the prose of §4. That is 75
table cells and 13 prose values; 2 of the prose values ("p ¡ 0.001", §4.1 and §4.2) are the
PDF's own rendering of `<` as `¡` and cannot be parsed, so 86 claims are verified and 2 are
recorded as unrepresentable.

**C1 on this paper:** `extract_claims(pdf_to_markdown(paper.pdf))` recovers **0** of the 86
(290 candidates rejected: 241 `outside_sections`, 49 `reference_numeral`). The claims here are
curated, not extracted; that gap is pinned by `tests/gate/test_agrodesign_fixture.py`.

Run-time files, written once by `tools/gate_run.py` (the only networked code; never imported
by tests):

| File | What it is |
|---|---|
| `trace.json` | the C3 `RunTrace` (`serialize_trace`); `parse_trace` reads it back |
| `objects/` | the run's locatable outputs (stdout and 21 CSVs — 21 objects, since two CSVs have identical bytes), each named by its SHA-256; stderr is left out (diagnostic-only, may carry local paths) |
| `verdicts.json` | the C4 verdict set (`serialize_verdicts`), replayed byte for byte by `tests/gate/test_agrodesign_replay.py` |
| `environment.txt` | the resolved environment (`uv pip freeze`) and the C2 descriptor |
| `drift.json` | the cross-check in an environment resolved with `--exclude-newer 2026-02-12` |

## The number (Phase 0)

| | |
|---|---|
| Claims in the rule | 88 (75 table cells + 13 prose values) |
| Representable as claims | 86 (2 × "p ¡ 0.001" cannot be parsed) |
| Recovered by C1 automatically | **0** of 86 |
| Bound to a value the run produced | **86** of 86 |
| `REPRODUCED` | **85** |
| `WITHIN-TOLERANCE` | 0 |
| `DIVERGED` | **1** (`review_required`) |
| `UNVERIFIED` | 0 |
| Verdicts changed in the older environment | 0 — its outputs are byte-identical (same `run_id`) |

Every `REPRODUCED` is within the paper's written precision (D1): e.g. Table 1 MS `363.333`
against the run's `363.3333333333342`, Table 4 F `5637.0` against `5637.000000000339`, Table 8
BLUP `7.7` against `7.677269579347461`. None needed a tolerance.

## Findings

These are discrepancies against the paper's **own** artifacts, recorded for review. They are
not claims that the paper's conclusions are wrong, and nothing here has been published or sent
to the author (R4; contacting the author is an owner decision).

1. **One reported value does not match its own code (`DIVERGED`).** §4.1 states the CRD
   residuals' Shapiro-Wilk test at "p-value = 0.034"; the package, run on the bundled CRD
   dataset, prints `p = 0.03455`, which rounds to 0.035. The paper's value looks truncated
   rather than rounded. It is a third-decimal reporting discrepancy, it does not change the
   stated conclusion ("a slight violation of normality"), and it is identical in an environment
   resolved as of the pinned code's date — so it is not environment drift. **Reviewed by the
   owner on 2026-09-27 and confirmed as a genuine reporting discrepancy** (R2's human review).
   The signed verdict keeps `review_required`; the review is recorded here, beside it.
2. **The documented workflow cannot complete as written.** The paper's appendix runs
   `result = Experiment(...).run()` then `result.export("results")`. With the default
   `plots=True`, `export()` raises `AttributeError: 'NoneType' object has no attribute
   'savefig'` for the CRD, RCBD, factorial and split-plot designs, because
   `agrodesign/plots/report_plot.py` never returns its figure. This holds at `v1.0.1` and at
   HEAD. The gate run uses `run(plots=False)`; no figure is a claim.

## Deviations from the paper's workflow (disclosed)

- `run(plots=False)` — finding 2.
- `mixed(["Genotype"], ["Block"])` — the API requires lists; the paper shows no mixed-model
  code. The bundled `mixed.csv` names its treatment column `Genotype`.
- Factor names per design are the bundled datasets' columns, as §4's prose names them.
- The driver prints `===== <design>` before each report, so each stdout binding matches once.

## Engine gaps this paper exposed (fixed test-first before the run)

- **Shortest-repr floats are not roundings.** pandas writes the exact 2.5 as `2.5`; C4 read the
  digits as precision and made the paper's `2.500` look finer than the run
  (`ARTIFACT_PRECISION_COARSER`, a harness-side false `UNVERIFIED`). Bindings now declare
  `"float_repr": true` for such artifacts; every CSV binding here does.
- **No trace loader.** `parse_trace` now reads `trace.json` back, run id re-checked.

## Known limits

- The claims are curated (by rule, grounded verbatim), not extracted — C1's 0/86 is the real
  extraction number on this paper. Why, from the rejections: §4 "Experimental Validation" is not
  recognised as a results section (241 `outside_sections`), and the tables arrive as
  whitespace-delimited text rows with glued tokens (`145.333<0.001`), not Markdown tables.
- The environment is resolved, not locked: the repo ships no lockfile, so C2's policy is
  "best-effort". `uv sync` also wrote `uv.lock` and `.venv` into the pinned checkout during the
  build (the run itself works in a copy); the tree hash was recorded before.
- The datasets are small, synthetic, author-constructed examples; this record shows the spine
  works end to end on a real paper's own code. It is not a scientific finding.
- This is not the Phase 0 gate's signed bundle: the verdict step replays offline from committed
  evidence, but a third-party *run-level* replay needs C6.
