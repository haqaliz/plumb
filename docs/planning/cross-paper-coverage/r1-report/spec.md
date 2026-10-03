# Spec — r1-report (cross-paper-coverage, aspect 3)

Source: `docs/planning/cross-paper-coverage/prd.md` R6 (approved 2026-10-02). Depends on:
`bank-flag` (built) + `panel-run` (closed 2026-10-02 with the documented-miss outcome).

## Problem slice

Publish the honest R1 measurement: the bank holds case #1 (AgroDesign: 86/86 bound, 85
`REPRODUCED`, 1 `DIVERGED`, precision/recall 1/1 `(owner)`); the panel search — fixed rule
written before selection, 4 candidates probed end-to-end — produced **0 additional
runnable papers**. The finding is the number itself (`cross-paper-coverage/prd.md` R4
fallback), reported with zero padding, and the named engine gaps that block panel growth
are recorded as follow-ons.

## In scope

- `docs/ROADMAP.md` — Phase 1 status updated (the R1 measurement exists and is ugly; the
  panel evidence; the named follow-on gaps).
- `docs/technical/CAPABILITY_ROADMAP.md` — C5 status written (store/bank/labels/metrics/
  report + `--bank` built; the R1 number; the blockages).
- `CLAUDE.md` — status paragraphs updated (C5 built; `--bank` in the CLI surface; the R1
  measurement replacing "unmeasured").
- No code changes; the suite stays green (docs-only).

## Out of scope

- Engine fixes for the named gaps (notebook capture, poetry env policy, figure locators) —
  each is its own follow-on unit, test-first, per the roadmap order.
- Relaxing the panel rule or re-selecting papers (anti-inflation; the rule was fixed
  before selection).
- The precision/recall benchmark over a public corpus (Phase 2).

## Acceptance criteria (written first)

1. `docs/ROADMAP.md` states the measured number (1 case: 86/86 bound, 85/1/0, 1/1
   `(owner)`), the selection yield (4 probed, 0 qualified), and the evidence path
   (`docs/planning/cross-paper-coverage/panel-run/screening.md`).
2. `CAPABILITY_ROADMAP.md` C5 has a Status section naming what shipped and the blockages.
3. `CLAUDE.md` no longer says "cross-paper coverage (R1) is unmeasured".
4. Nothing overclaims: no paper count, coverage rate, or precision figure beyond what the
   bank and the screening note evidence; `UNVERIFIED`/selection-miss language is honest.
5. `uv run pytest -q` stays green (docs-only change).