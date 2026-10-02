# Spec — discrepancy-corpus / benchmark

Source: `docs/planning/discrepancy-corpus/prd.md` requirements R5, R6 (labels read), S3.
Date: 2026-10-01.

## Problem slice

The calibration instrument: given a store of banked cases plus human labels, compute
per-claim coverage / precision / recall with the honest-number rules — `UNVERIFIED` excluded
from precision, unlabeled `DIVERGED`s counted in neither numerator nor denominator, every
figure carrying its denominator and a label-authority marker (`owner` / `third-party`),
canonical JSON output. This is the R1 measurement surface.

## In-scope

- Coverage: bound/claims per case and across the store, using the C4 bound definition
  (`docs/planning/binding-verdict/prd.md:179-181`); `UNVERIFIED` counted in coverage but
  never folded into pass/fail rates.
- Precision on `DIVERGED`: confirmed / (confirmed + refuted); recall: confirmed / flagged
  problems; per-claim denominators; label-authority marker per case.
- `labels.json` reading (canonical, claim-keyed, `confirmed` / `refuted`, absent =
  `unlabeled`); the engine never writes or suggests labels.
- `plumb corpus report [--store DIR]`: table or canonical JSON, byte-identical across
  processes/seeds, honest when the first numbers are ugly (n=1 shown as `1/1
  (owner-labeled)`, never a bare rate).
- Synthetic corpus tests exercising the `UNVERIFIED`-exclusion math (case #1 has 0
  `UNVERIFIED`, so exclusion is only provable synthetically in this slice).

## Out-of-scope

- Public benchmark publication or export (R5 egress).
- Third-party labeling flow; label writing.
- Thresholds/policy ("refuse to emit precision when owner-only" was raised at the review
  gate and resolved **as-is**: marker, not refusal — the PRD's approved wording stands).

## Acceptance criteria (tests written first)

1. Precision math: a synthetic store mixing `REPRODUCED` / `DIVERGED` / `UNVERIFIED` with
   labels proves `UNVERIFIED` never enters precision; an unlabeled `DIVERGED` is counted in
   neither numerator nor denominator; confirmed counts exactly the labeled-confirmed set.
2. Coverage matches the C4 bound definition and never folds `UNVERIFIED` into a pass/fail
   rate.
3. The report carries a denominator and label-authority marker on every figure; a
   single-owner-confirmed `DIVERGED` renders as `1/1 (owner-labeled)`.
4. Report bytes are canonical: byte-identical across processes and `PYTHONHASHSEED` values,
   no timestamps, no absolute paths.
5. Case #1 (banked AgroDesign) produces the expected first numbers: coverage 86/86 bound,
   1/1 `DIVERGED` confirmed (owner-labeled), 85/86 `REPRODUCED`.
6. Exit contract: 0 on report, 1 on any named cause (e.g. missing store), 2 on usage; no
   network; full suite green.

## Dependencies & sequencing

- Requires `store` (read cases) and a banked case #1 (from `bank`).
- Uses only human labels; no model anywhere (guardrail: execution-grounded, engine never
  labels).

## Open questions / risks

- Recall's "flagged problems" denominator needs a concrete definition for the slice:
  proposed = all claims a human labeled `confirmed` **plus** all `DIVERGED`s a human
  labeled `confirmed` or `refuted`… to be pinned in the plan (the PRD says
  "confirmed-DIVERGED / human-flagged problems" — interpret "flagged" as
  label-attached-to-DIVERGED for this slice and state it).