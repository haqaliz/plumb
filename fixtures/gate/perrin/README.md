# Gate fixture: Perrin et al. (arXiv:2401.11842)

The second panel paper of the cross-paper-coverage aspect
(`docs/planning/cross-paper-coverage/panel-run/`), run through Plumb's spine (C2 intake →
C3 run → C4 bind & verdict). Planning and screening: `docs/planning/cross-paper-coverage/panel-run/`
(the selection rule, the screening note's candidate #3, and the panel decision).

## Provenance

| | |
|---|---|
| Paper | Valentine Perrin, Nathan Noiry, Nicolas Loiseau, Alex Nowak, *Subgroup analysis methods for time-to-event outcomes in heterogeneous randomized controlled trials*, arXiv:2401.11842v2 [stat.ME], 23 Jan 2024 |
| Paper licence | [CC BY 4.0](http://creativecommons.org/licenses/by/4.0/) (stated on the arXiv abs page) — `paper.pdf` is redistributed unmodified, with attribution |
| Paper source | `https://arxiv.org/pdf/2401.11842v2`, fetched 2026-10-03 (owner-authorized dev-time fetch) |
| `paper.pdf` SHA-256 | `f40dd4124c16b2c37d929fa1f1f2936c8d69816c58dcf94aff2da817e909144c` |
| Code | `https://github.com/owkin/hte`, Apache-2.0 — **not vendored**; resolved at run time by `tools/perrin_gate_run.py` |
| Pinned rev | `76ce145f42fd37a91b389d8c8762de167647f82f` (2024-01-19, "Update README.md") — the last commit before the arXiv submission (v1, 22 Jan 2024); the repo has no tags; the only later commit (`6218ab6`, 2024-06-27) changes one README line and nothing else |
| Data | none downloaded: the DGP is synthetic (Gaussian covariates, Weibull/Cox survival, seed-controlled per §A.3); the semi-synthetic covariate pool is the committed `hte/configs/data_configs/semi_synthetic_p1000.csv` (TCGA-derived, bundled in the repo); the ARR grids are committed `data/results_compute_arr/*.json` (the paper's own DGP outputs) |

## Files

| File | What it is | Written by |
|---|---|---|
| `paper.pdf` | the paper | fetched once |
| `claims.json` | the rule-defined claim set, each claim at its verbatim span in `normalize_text(pdf_to_markdown(paper.pdf))` | `tools/perrin_spec.py` |
| `unrepresentable.json` | members of the rule that do not become claims, each with the reason | `tools/perrin_spec.py` |
| `bindings.json` | one binding per claim | `tools/perrin_spec.py` |
| `source.json` | the `SourceRecord` the code was resolved from (for `--out` bundle rebuilds; `plumb verify --from-record` reads it) | hand-written, rev pinned at probe time |

## The claim rule (fixed before any run or binding, 2026-10-03)

**Every numeric performance cell of the paper's main-text results tables**: Table 1
(type I error of each method, §6.1) and Tables 2–4 (semi-synthetic power / averaged
precision / accuracy, §6.4). The ARR column (the experiment's independent variable, a
design grid) and the "–" cells (explicit non-values for methods the paper did not run at
p=100/p=1000) are not rule members.

A rule member becomes a claim only if the paper's own code can re-derive its scenario
within the panel's dev-time budget on this machine (14 cores; probe measurements below):

- **Claims — 16 cells**: Table 1's p=20 column (9 cells) and p=100 column (7 cells).
  The type-I-error scenario (1000 repetitions of the DGP at ARR=0, sampling size 500,
  0.5/0.5 split, first censoring scenario — Table 1's caption) re-derives in ≈ 2.1 h
  (p=20: 107 s per repetition over 9 methods incl. SIDES/SeqBT) and ≈ 47 min (p=100:
  39 s per repetition over 7 methods).
- **Recorded non-claims — 217 cells, with reasons**: Table 1's p=1000 column (7 cells)
  and Tables 2–4 (210 cells). Probe measurements: ARDP's p=1000 fit alone ≈ 15.5 min
  per repetition (930 s), so the p=1000 type-I-error scenario (1000 repetitions) is
  ≈ 24 CPU-hours and the semi-synthetic scenario (100 repetitions × 10 ARR points × 8
  methods at p=1000) is ≈ 21 CPU-hours on this machine — cluster-scale, outside the
  panel's laptop-CPU budget. Recorded, not forced (the screening note's runtime caveat,
  `screening.md` §4; the plan's escape hatch, `plan_20261002.md`). These are not
  parse-failures: they are representable values whose scenarios cannot be re-derived
  within the budget, and `unrepresentable.json` carries each with its measured reason.

Row-label mapping (paper text → pipeline `method`): `Univariate t-test` → `Univariate
t_test`; `Multivariate Cox` → `Multivariate cox`; `Multivariate Tree` → `Multivariate
tree`; `IT` → `ITree`; `Oracle` is run by the pipeline but not reported in Table 1, so
it is not a rule member.

## Panel framing

The paper is a **benchmarking paper**: it compares 9 subgroup-analysis methods on
simulated time-to-event RCT data and reports method performance. The claims verified
here are the paper's Table 1 type-I-error values at p=20 and p=100 — the fraction of
1000 null-hypothesis repetitions in which each method returned p < 0.05. The claim
mix is deliberately stated: unlike AgroDesign's design-inference numbers, these are
aggregates over a seeded Monte-Carlo benchmark; a `REPRODUCED` means the paper's
reported rate was re-derived from the repo's own run within the written 3-decimal
precision, nothing more.

**Expected-tension note (probe finding):** the repo's *committed* type-I-error CSVs
(`experiments/results_expe/processed_results/dim_20.zip` / `dim_100.zip`, the authors'
own runs, 1000 repetitions, first censoring scenario) already disagree with the
paper's printed Table 1 on several cells — e.g. p=20 Univariate t-test: committed mean
0.043 vs printed 0.035; p=100 MOB: 0.058 vs 0.043. Whether the paper's printed numbers
are re-derived by the repo's own run is exactly what the verdicts decide; the committed
CSVs are never read (stale, `CLAUDE.md` #5).

## Known deviations from the paper's workflow (disclosed)

- **Environment**: the repo ships a poetry project (poetry.lock, Dec 2023). The engine
  builds via `uv sync`, but modern uv (0.12.17) no longer reads `[tool.poetry]` /
  `poetry.lock` and produced an **empty** environment (probe). The paper-era boundary
  (`--exclude-newer 2024-01-23`, the M4a pattern) cannot build either: `qdldl 0.1.7.post0`
  (via osqp ← scikit-survival) has no macOS arm64 wheel and its sdist fails to compile
  on this toolchain (missing generated header, even with CMake 4.4.3 installed). The
  environment is therefore resolved at **`--exclude-newer 2024-06-18`** (Python 3.10;
  qdldl 0.1.7.post3 is the first arm64-wheel release, 2024-06-17) — the earliest
  boundary this machine can build. Recorded as drift, not assumed away (M4a).
- **Output naming**: the pipeline names its CSVs with a wall-clock timestamp
  (`..._<MONTH>_<DAY>_<YEAR>_<TIME>.csv`). The driver copies each fresh CSV to a
  canonical name for binding; the bytes are untouched.
- **Reduction**: Table 1's values are the analysis notebook's reduction of the fresh
  processed CSV — the mean of `thresh_pval` per method over the 1000 repetitions at
  `scale=1.0` (the first censoring scenario). The driver computes exactly that from the
  pipeline's own fresh output.
- The driver runs the type-I-error scenario as Table 1's caption specifies: ARR=0 only
  (`-n=1`), 1000 repetitions, sample size 500, 0.5/0.5, censored, scale 1.0, at p=20
  (all 9 reported methods) and p=100 (7 methods; SIDES/SeqBT excluded — the paper's
  "–" cells).

## Known limits

- The verified claims are a scoped, rule-defined subset of the paper's headline numbers
  (16 of 233 numeric cells of Tables 1–4); the other 217 are recorded non-claims with
  the measured runtime reason. The p=1000 and semi-synthetic scenarios are cluster-scale
  on this machine and were not forced through.
- Determinism (probe): the pipeline is seed-controlled (`np.random.seed(42)` at launch
  and at module import; per-repetition seeds drawn from the seeded parent RNG), but
  survival-time draws use the global RNG inside joblib workers, whose draw order depends
  on worker scheduling. Empirically the pipeline was byte-identical across five probe
  runs (raw and processed CSVs) on this 14-core machine; a machine with a different
  core count may produce different draws, and the recorded run's verdicts bind to what
  this machine produced.
- The environment is resolved, not locked (no uv.lock; the poetry.lock is unreadable by
  modern uv). The boundary date and the toolchain deviation are recorded above.
- C1 recovery on this paper is measured and reported in the README's recovery section
  (see `tests/gate/test_perrin_recovery.py`); this paper's C1 extraction may differ from
  the curated set (layout-heavy tables) — the number is reported, not tuned.

## C1 recovery (measured 2026-10-02, reported as measured — never tuned)

`extract_claims(pdf_to_markdown(paper.pdf))` vs the curated set, matched by **place and
value** (`tests/gate/test_perrin_recovery.py`):

| | |
|---|---|
| recall | 1.000 — all 16 curated cells recovered (16/16) |
| precision | 0.207 — 103 of 498 extracted claims are real paper cells (against the full rule: curated + the 217 runtime-gated members, which are true positives, not defects) |
| extras | 395 layout numerals — β coefficients, section numbers, list markers — genuine extraction noise on this layout-heavy paper, reported, not retuned |
| shared ids | 71 of 319 distinct ids span multiple locations, all same-value repeats (value-identity dedup, never two different values under one id) |

## The number (this fixture)

| | |
|---|---|
| Claims in the rule (Tables 1–4 numeric cells) | 233 |
| Claims verified (Table 1, p=20 and p=100 columns) | 16 |
| Recorded non-claims (out of the panel's budget) | 217 |
| Bound to a value the run produced | to be recorded by `tools/perrin_gate_run.py` |
| `REPRODUCED` / `DIVERGED` / `UNVERIFIED` | to be recorded by `tools/perrin_gate_run.py` |

Run-time files (written once by `tools/perrin_gate_run.py`, the only networked code;
never imported by tests): `trace.json`, `objects/` (locatable only), `verdicts.json`,
`environment.txt`, and — only where a `DIVERGED` appears — `drift.json`. `labels.json`
is never created (owner review is separate).

## Owner review of the 13 DIVERGEDs (2026-10-02, delegated)

**Conclusion: all 13 confirmed as genuine reporting discrepancies** — the paper's printed
Table 1 rates are not re-derivable from its own artifacts. Evidence:

1. **Two independent runs contradict the printed table.** The authors' own committed
   results (`experiments/results_expe/processed_results/dim_20.zip`, `dim_100.zip`)
   disagree with the printed values in places where the fresh run **agrees** with the
   paper (p=20 Univariate t-test: committed `0.043` vs printed `0.035` vs fresh `0.035`;
   p=100 MOB: committed `0.058` vs printed `0.043` vs fresh `0.043`). The env-boundary
   deviation (2024-06-18 vs paper era) cannot explain the 13: two unrelated resolutions
   of the repo both fail to reproduce the printed numbers.
2. **No harness-side failure.** The run succeeded (exit 0, no run-level causes) on the
   pinned tree `76ce145f`; every binding reads a fresh, hash-verified captured output
   (csv_cell on the run's own reduced CSVs); every DIVERGED carries its written-precision
   band and delta (e.g. `0.060` vs `0.064`: outside [0.0595, 0.0605]).
3. **The pattern is not a rounding artifact.** Deltas run 0.001–0.010 in both directions
   (e.g. p=20 SIDES `0.125` printed vs `0.119` run; p=100 ARDP `0.049` vs `0.039`) —
   outside written-precision bands, with no systematic offset.
4. **Caveats recorded, not waived:** the M4a drift cross-check is inconclusive by
   construction on this machine (no second runnable env; `drift.json`); the recorded
   environment is the earliest buildable boundary. The review weighs the two-runs
   evidence above as decisive for the printed values being the anomaly.

`labels.json` marks all 13 `confirmed` (transported by the bank, never created by the
engine); the case is re-banked so the labels land in the manifest. The signed verdicts
keep `review_required` — the label is the human review, the verdict the execution.
