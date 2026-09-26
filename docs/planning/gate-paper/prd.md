# PRD — the first real paper through the spine (`gate-paper`)

Source: `docs/planning/_card/issue.md` (inline brief; the owner delegated the pick) and
`docs/planning/_card/understanding.md` (deep dig and feasibility spike). Candidate screening:
`survey.md` alongside this file.

**Status (2026-09-26): landed** — 86 claims, 86 bound, 85 `REPRODUCED`, 1 `DIVERGED`; M4a
drift check: byte-identical outputs in the older environment. One plan-time addition: the
`float_repr` binding flag (engine gap). The record: `fixtures/gate/agrodesign/`.

## Problem Statement

C1–C4 are built and have emitted verdicts only on synthetic repos. Phase 0's question — *what
fraction of a real paper's headline claims can we bind and re-derive, and how many DIVERGE* —
has never been asked of a real paper (`docs/ROADMAP.md`). Until it is, R1 (binding coverage)
and R2 (false `DIVERGED`) are unmeasured, and C5/C6 have nothing real to bank or bundle.

## Goals & Success Metrics

- **G1 — The number, on a real paper.** A committed gate record for AgroDesign
  (arXiv:2603.09041) states: claims attempted, claims bound, per-verdict and per-cause counts,
  produced by the built C2 → C3 → C4 spine on the paper's own code at a pinned commit.
- **G2 — C1's own number, next to it.** The same record states C1's automatic recovery on this
  paper (today 0 of the curated claims), with the rejection causes — so the curated set cannot
  be mistaken for extraction coverage.
- **G3 — Offline replay of the verdicts.** A test re-derives every verdict from the committed
  captured outputs and asserts the committed `verdicts.json` byte for byte. No network.
- **G4 — Honest framing.** Every `DIVERGED` is `review_required`, framed as a discrepancy
  against the paper's own artifact, and not published.

## Decisions (recommended; for approval at the review gate)

- **P1 — The paper.** AgroDesign, Aqib Gul, arXiv:2603.09041v1, CC BY 4.0 (the PDF may be
  committed as a fixture with attribution). Code `github.com/DeepStatistix/AgroDesign`,
  Apache-2.0, pinned at tag **v1.0.1** (`18b7c29a4f`, 2026-02-12, "Paper corrections done" —
  the last code change before the 2026-03-10 submission; `src/` is byte-identical to HEAD).
- **P2 — Claims are curated and span-grounded.** C1 admits none from this paper (see G2), so the
  gate uses a hand-curated claim set. **The set is defined by a rule fixed before binding, not
  by choice:** every numeric cell of Tables 1–8 (DF, MS, F, p-value, variance, BLUP) and every
  test statistic stated in the text of §4 — all of them, including any that turn out not to
  bind. Selecting claims after seeing the spike would inflate the number (the spike already
  showed which values reproduce). Each is a real `Claim` whose `reported_value.text` must occur **verbatim** at its
  `CharSpan` in the normalized paper text — a test enforces it, so no curated claim can be a
  value the paper did not write (constraint #1, R3). Metric names are descriptive
  (`"CRD ANOVA Treatment MS"`). The curated set doubles as labels for the C1 follow-on.
- **P3 — The driver is an explicit argv that transcribes the paper's workflow.** The repo has
  no entry point, so C3's "explicit wins" path runs `python -c <driver source>`, recorded
  verbatim in the trace (no absolute paths). The driver does, per design, what the paper's
  appendix does — `Experiment(...).<design>(...).run()`, `print(result)`,
  `result.export(...)` — with two **disclosed** deviations: `run(plots=False)` (the package's
  `report_plot()` returns `None`, so `export` crashes with the default at v1.0.1 and HEAD), and
  `mixed(["Genotype"], ["Block"])` (the API requires lists; the paper shows no mixed-model
  code). Factor names come from the paper's section text and the bundled datasets.
- **P4 — The environment is built once, at dev time.** `tools/gate_run.py` does the authorized
  network work: `resolve_git` at the pinned rev, `describe_environment`, a real
  `build_environment` (no lockfile → the "declared" policy), then the offline run. The resolved
  versions (`uv pip freeze`) are frozen into the record, because the paper's own environment is
  unknown (ranges only) — env drift is recorded, not assumed away.
- **P5 — The gate record is committed** under `fixtures/gate/agrodesign/`: the PDF and
  provenance README (source URLs, licenses, SHA-256), `claims.json` (via
  `plumb.extract.serialize`), `bindings.json`, `trace.json` (`serialize_trace`), the captured
  locatable outputs (stdout and the CSVs, stored by SHA-256 — kilobytes), `verdicts.json`
  (`serialize_verdicts`), `environment.txt`, and a `README.md` with the number and the
  findings.
- **P6 — Findings are not published.** The expected `DIVERGED` (CRD Shapiro-Wilk: paper
  `0.034`, run `0.03455`; correctly rounded, `0.035`) and the export defect are recorded in the
  fixture README, framed as reporting/reproducibility discrepancies against the paper's own
  artifact. Contacting the author (R4 right of reply) is an owner decision, out of scope here.
- **P7 — Gate status is stated exactly.** This produces the Phase 0 number on a real paper.
  The gate also asks for "a bundle a third party can replay"; the committed record replays the
  *verdict* step offline, but it is not the signed, run-replayable C6 bundle. The docs will say
  **"number produced; bundle pending (C6)"**, not "gate met".

## Requirements

### Must-have

- **M1 — Fixture & provenance.** The PDF, its SHA-256, the arXiv and repo URLs, both licenses,
  the pinned rev and the checkout's tree hash; a test checks the PDF hash.
- **M2 — Curated claims, grounded.** `claims.json` loads into `Claim`s; for every claim,
  `normalize_text(paper)[span]` equals `reported_value.text` — or, where the converter glues
  tokens (`145.333<0.001`), the claim's text is a verbatim substring at its span. Duplicate
  claim ids are refused.
- **M3 — C1 coverage recorded.** A test runs `extract_claims(pdf_to_markdown(pdf))` and records
  how many curated claim ids it recovers (today 0) and the rejection causes; the number is
  written to the record, and the test pins it so an improvement is visible (it will be updated
  by the C1 follow-on, never silently).
- **M4 — Bindings.** One binding per curated claim: `csv_cell` into each design's
  `anova_table.csv` (row key = the index column, e.g. `C(Treatment)`), `stdout_regex` for the
  Shapiro-Wilk values, variance components and BLUPs, anchored to the design's section of the
  report so each matches exactly once.
- **M4a — The DIVERGED is cross-checked against drift.** Before a `DIVERGED` is recorded, its
  value is recomputed in a second environment resolved with older pins (the newest releases
  available before 2026-02-12 for scipy/statsmodels/numpy/pandas). If the two environments
  disagree on the verdict, the claim is recorded `UNVERIFIED` with the drift noted in the README
  (it is not a C4 cause, so the README explains it) and not counted as `DIVERGED`. (R2.)
- **M5 — Offline replay.** `tests/gate/` rebuilds a `Capture` from the committed objects,
  checks every object's hash, re-derives the verdicts with `verify_claims`, and asserts
  byte-identity with `verdicts.json` and the expected per-claim table.
- **M6 — The dev-time run.** `tools/gate_run.py` is the only networked code, never imported by
  tests, and writes the whole record; re-running it on the same machine reproduces
  `verdicts.json` byte for byte (the run id may differ only if the outputs differ).

### Should-have

- **S1** — The fixture README carries the per-verdict table, the C1 number and causes, the two
  findings, the deviations, and the environment freeze.
- **S2** — Docs: `CLAUDE.md`, `README.md`, `CAPABILITY_ROADMAP.md`, `ROADMAP.md` (Phase 0 line:
  number produced, bundle pending), the survey linked.

### Nice-to-have

- A C1 follow-on card drafted from M3's causes (results-section names; whitespace-delimited PDF
  table rows; glued `value<bound` tokens).

## Technical Considerations

- **C2–C4 on a real repo**, no new engine code expected: `resolve_git`, `describe_environment`,
  `build_environment`, `run_and_capture` with an explicit `EntryPoint`, `load_bindings`,
  `verify_claims`, the serializers. If a real repo breaks an engine assumption, that is fixed
  test-first in the engine, not worked around in the tool.
- **Determinism:** the verdicts depend only on the committed captured bytes; the replay test is
  the determinism check. CSV floats reach C4 as text and are parsed as strict decimals.
- **Size:** the PDF is ~1.5 MB; captured outputs are a few KB. The repo itself is not vendored.
- **Verdict impact:** execution decides every verdict; claims are curated but grounded
  verbatim; no model anywhere.

## Risks & Open Questions

- **R1** — the whole point: the number will show C1 recovering 0 of ~35 on this paper. That is
  a finding, and it is reported.
- **R2** — the one expected `DIVERGED` is a third-decimal truncation. It is real under the
  paper's written precision (D1), and exactly the kind of result `review_required` exists for;
  it must not be summarised as "the paper is wrong".
- **R2 / env drift** — library versions are newer than the author's (unknown). Every checked
  value matched in the spike, and the Shapiro-Wilk value is far from any version-sensitive
  regime, but the record says which versions ran.
- **R3** — curation error: a mis-transcribed claim would be caught by the span-grounding test.
  A wrong *binding* (pointing at the wrong row) is the residual risk; the bindings are reviewed
  in the fixture README.
- **R4** — named paper, named author: nothing is published; contact is an owner decision.
- **Open:** Table 8's `G1` BLUP does not survive text extraction — confirm against the PDF at
  plan time and bind only what the paper text contains.

## Self-critique (prd-generator, 2026-09-26)

| Dimension | Rating | Note |
|---|---|---|
| Problem | 🟢 | Phase 0's question, never asked of a real paper |
| Metrics | 🟢 | Each goal is a committed artifact or a test |
| Scope | 🟢 | C6 and the C1 fix are explicitly out |
| Risks | 🟡 | Env drift on the one DIVERGED — mitigated by M4a, not eliminated |
| Verdict honesty | 🟡 → fixed | Curation bias: the claim set is now rule-defined and exhaustive (P2) |
| Feasibility | 🟢 | The spike ran every design end to end |

**Hard question:** the datasets are small, clean, author-constructed examples and the paper is a
software paper. The run proves the spine works on a real paper end to end, and the numbers are
genuinely the paper's — but a third-decimal truncation is not a *finding* anyone would act on.
Is this acceptable as the first gate paper, with a scientifically weightier one as the second?

## Out of Scope

- C6 signing/bundling; a run-level replay.
- Fixing C1 for this paper (a follow-on, labelled by the curated set).
- Notebook capture; any change to the paper's code; contacting the author; publishing.
