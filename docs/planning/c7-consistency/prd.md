# PRD — C7 statcheck/GRIM internal-consistency path

Issue: #23.

## Requirements

- **R1** — `plumb consistency <paper> [--json]`; `.md` or `.pdf`; exit 0 = nothing inconsistent,
  1 = at least one inconsistency, 2 = usage. Never a traceback.
- **R2** — statcheck recomputes p for explicitly reported `t(df)`, `F(df1, df2)`, `χ²(df)`,
  `z`, `r(df)` with a df and a p, using no new dependency.
- **R3** — conservatism: both-sided comparison for `t`/`z`/`r`; bound-aware; precision-band;
  missing df → `NOT_APPLICABLE`.
- **R4** — GRIM on `mean =` + `N =` in one sentence, exact Decimal arithmetic, boundary
  documented.
- **R5** — labels `INTERNAL_INCONSISTENCY` / `CONSISTENT` / `NOT_APPLICABLE` only; no verdict
  word appears in code or output; a test asserts it.
- **R6** — the report carries the paper's SHA-256 in JSON for provenance.

## Non-goals

- Calibrating against a labeled no-code corpus (no such corpus yet).
- One-tailed conventions, symmetric-χ² variants, p-curve/statcheck's full rule set.
- Any interaction with bundles or verdicts.

## Acceptance

`tests/consistency/test_consistency.py` (29 tests incl. known critical values); full suite green.
