# PRD — C1 claim recovery on the gate paper (`claim-recovery`)

Source: `docs/planning/_card/issue.md` (inline brief from `plumb-next`) and
`docs/planning/_card/understanding.md` (the deep dig and probe). Capability: **C1**
follow-on slice (`docs/technical/CAPABILITY_ROADMAP.md`). Owner accepted decisions D1–D8
wholesale on 2026-09-27.

## Problem Statement

The Phase 0 gate was met on AgroDesign (arXiv:2603.09041) with **86 curated claims** — and
C1 recovered **0** of them (`fixtures/gate/agrodesign/README.md`). Every number in §4
"Experimental Validation" is refused `outside_sections` because that title is not in the
literal heading list (`src/plumb/extract/candidates.py`, `_HEADING_SECTIONS`). Phase 1's
`plumb verify <paper> <repo>` cannot be real while the claim step is hand-written.

The probe (understanding note) shows the fix is not one line. Mapping the heading alone
recovers 85/86 but **creates** 14 non-curated claims, two of them dangerous (`p ¡ 0.001` —
LaTeX OT1's rendering of `<` — admitted as the Point `0.001`, a value the paper never wrote),
and 9 id collisions between distinct table cells (`Nitrogen 2 433.500 433.500<0.001` gives
MS and F the same `(text, metric, units)`). Recall without precision and identity would be
worse than 0/86: it would hand C4 false and ambiguous claims (R3, and via a false Point,
R2).

## Goals & Success Metrics

Measured on `fixtures/gate/agrodesign/` by a committed test, not by prose:

| Metric | Floor | Target |
|---|---|---|
| Recall vs the 86 curated claims (D2 match) | ≥ 0.95 | 86/86 |
| Precision (claims matching a curated claim ÷ claims emitted) | ≥ 0.95 | 1.0 |
| Claims whose value comes from `¡`/`¿` + number | **0** | 0 |
| Id collisions between claims at distinct table cells | **0** | 0 |
| Every non-recovered curated claim | carries a named cause | — |

No regression (all existing tests, unchanged): the five `fixtures/papers/` recovery floors,
the 73-row blind selection score (1.0/1.0), PDF↔Markdown claim-id equality
(`tests/extract/test_pdf_seam.py`), and the committed AgroDesign bundle still verifies.

## User Personas & Scenarios

A reviewer or lab runs Plumb on a paper whose results section is not literally titled
"Results" and whose tables arrive from the PDF as whitespace rows. Today they get zero
claims and must hand-write every one. After this slice they get the paper's claims
automatically, each named well enough to bind to one artifact value — and never a claim the
paper didn't make.

## Requirements

### Must-have

- **M1 — Section title (D1).** `"experimental validation"` maps to `results` in
  `_HEADING_SECTIONS`, a literal entry with its own test. No fuzzy matching.
- **M2 — Recovery measure (D2).** A curated claim is recovered when an emitted claim's
  location lies within the curated span and the parsed `ClaimValue`s are equal. Not by
  `Claim.id` (it hashes the metric, and curated metrics are hand-written).
- **M3 — Unreadable comparator (D3).** A number directly preceded (spaces allowed) by `¡` or
  `¿` is refused at the gate as `partial_value` — the glyph is a comparator the value
  parser cannot read, so the bare number is a fragment. No repair; the two stay in
  `unrepresentable.json`.
- **M4 — Layout numerals (D4).** A new selection cause `layout_numeral`, added to the closed
  `SELECTION_CAUSES` with a test, refuses: the numbering prefix of a heading line
  (`# 4 …`, `## 4.1 …`); a line whose whole content is one bare integer (a page number);
  a line-leading list marker (`1. `).
- **M5 — Significance level (D5).** `α`, `alpha`, `significance level` join the
  `hyperparameter` cues (a set design input, not a result). `α` is matched without a
  leading word boundary (the PDF writes `atα= 0.05`).
- **M6 — Whitespace tables (D6).** `extract/tables.py` recognises a caption-led whitespace
  table — a `Table N:` caption line followed by consecutive rows of a text label and one
  or more numeric/dash cells, with glued `value<bound` cells split — as a table. Its cells
  carry `section_hint = table` and a metric naming table number, row label and column
  (the header row's text where the paper wrote one, else a column ordinal). Result: no id
  collision between distinct cells.
- **M7 — Floors (D7).** The table above, as committed tests.
- **M8 — The pinned gap moves (D8).** `tests/gate/test_agrodesign_fixture.py`'s 0/86 pin
  becomes the floor test; the fixture README, `CLAUDE.md` and `CAPABILITY_ROADMAP.md`
  report the new number and what remains.

### Should-have

- A per-cause breakdown of the AgroDesign rejections in the fixture README (C5 wants the
  causes countable).

### Nice-to-have

- A second real paper's recovery measured with no new code (evidence against overfitting).

## Technical Considerations

- **Capability C1 only.** No verdict code changes; execution still decides every verdict.
  The curated `claims.json`, `bindings.json` and the signed bundle are untouched — the
  extracted set is *measured against* them, not substituted for them.
- **The converter is frozen for this paper.** `verify_bundle` re-runs `pdf_to_markdown` and
  re-admits claims at recorded offsets (`src/plumb/bundle/verify.py:189,241`); a converter
  change to AgroDesign's text breaks the signed bundle. All changes live in `extract/`.
- **Closed vocabularies.** `layout_numeral` is a new selection cause; the gate's
  vocabulary is unchanged (M3 reuses `partial_value`). The disjointness test between the
  two vocabularies must still pass.
- **Ordering.** The layout check runs after the section check and before the lexical
  categories; its place in the check-order docstring is part of the contract.
- **Whitespace-table detection must not fire on prose.** Required: caption line matching
  `^Table \d+[:.]`, then ≥ 2 consecutive rows; a row ends the table when it has no numeric
  cell. Detection is additive to GFM pipe tables — a pipe table is never re-read.
- **Determinism.** All rules are regex/line structure; byte-identical output across
  processes is already pinned by `tests/extract/test_determinism.py`.

## Risks & Open Questions

- **R3 (claim-extraction error).** The whitespace-table rule could promote a wrapped prose
  line after a caption into a "row". Mitigation: caption-led only, ≥ 2 rows, stop on the
  first non-row; tested against all five fixtures via the seam test.
- **Overfitting to one paper (R3/R6).** Each rule is stated generally and tested on
  synthetic text as well as AgroDesign; the five fixtures are the regression net.
- **Page-number rule false negatives.** A real value wrapped alone onto its own line would be
  refused `layout_numeral` — the safe direction (a false negative, named), not a false claim.
- **Tables with no header text** (Tables 2–4, 7 here) get ordinal column names — honest, but
  C4 bindings must address "column 3" rather than "MS". Acceptable for this slice.
- **Open:** whether a header-less table should inherit column names from an earlier table
  with the same shape. Out of scope — it would be an inference, not a reading.

## Out of Scope

- Any change to `src/plumb/pdf/` (converter), `claims.json`, `bindings.json` or the bundle.
- Repairing `¡`/`¿` to `<`/`>`.
- A BYOK/LLM proposer, a binding proposer, the `plumb verify` CLI.
- Fuzzy section matching; new section hints.
- Recall on papers other than AgroDesign beyond the existing fixture floors.

## Self-critique (prd-generator, 2026-09-27)

| Dimension | Rating | Note |
|---|---|---|
| Problem clarity | 🟢 | Probe-backed, with numbers |
| Success metrics | 🟡 | Precision is measured against a *curated rule*, not "is it a claim" — see gap 2 |
| Scope | 🟢 | Converter/bundle freeze explicit |
| Requirements testability | 🟢 | Every M has an acceptance test in a spec |
| Risks | 🟡 | Gaps 1 and 3 below |
| Stakeholders | 🟢 | Owner approves; solo build |
| Feasibility | 🟡 | Gap 1 is the unknown in `whitespace-tables` |
| Verdict honesty | 🟢 | C1 only; the change *removes* a latent false `DIVERGED` path (`¡ 0.001` as a Point) |

**Gap 1 (🟡, feasibility) — the whitespace-table rule fires on three fixture PDFs.** The
caption pattern matches on the PDF path of PMC12780771 (2), PMC13298092 (5) and PMC13363872
(20). There, the Markdown path has pipe tables; if the PDF path now yields table cells with
new metrics, claim ids diverge and the seam test (`test_pdf_seam.py`) can move. Fix: the
plan's first task in `whitespace-tables` measures the seam before/after; the table metric
must be derivable identically from a pipe table and a whitespace table, or the recogniser
is gated so it only fires where no rows would otherwise be table cells. Decided in the plan
with the measurement in hand, not assumed.

**Gap 2 (🟡, metrics) — precision against the curated rule.** The rule covers table cells and
§4 F/p/Shapiro-Wilk prose values. A genuine claim outside it (e.g. §4.6's heritability
`H 2 = 0.99`) would count as a false positive. Fix: precision's denominator excludes claims
on a small, committed, reviewed allow-list of rule-external genuine claims, each with a
reason; the list is empty unless the run shows one.

**Gap 3 (🟡, silent drops) — `layout_numeral` can drop fixture claims no test sees.** The
seam test compares the two paths, so a rule that drops a claim on both passes; the blind set
is abstract-only. Fix: `sections-precision` records per-fixture claim counts before/after
in the PR, and every dropped claim is listed with its cause and reviewed.

**Known quirk:** Table 8's header row arrives as the heading `## Genotype BLUP`, so Table 8
gets ordinal columns unless a heading line directly after a caption is read as the header.
The spec leaves it ordinal (honest); a later slice may read it.

**The question to answer before greenlighting:** if the whitespace-table metric can't be made
identical to the pipe-table metric for the same cell, which path's naming wins — and does
changing the fixtures' PDF-path ids count as a regression or as the seam test's expectation
changing?

## Aspects

1. `sections-precision` — M1–M5, M2's measure, the precision floor on non-table claims.
2. `whitespace-tables` — M6, the id-collision floor, then M7/M8 on the full set.
