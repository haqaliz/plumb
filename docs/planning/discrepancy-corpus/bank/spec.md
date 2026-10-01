# Spec — discrepancy-corpus / bank

Source: `docs/planning/discrepancy-corpus/prd.md` requirements R3, R4, R6. Date: 2026-10-01.

## Problem slice

The user-facing surface that turns a verify record into a banked case: `plumb corpus bank
<record-dir> [--store DIR]`, re-deriving the verdicts from the stored trace before banking
(never trusting committed `verdicts.json` alone), folding the committed AgroDesign record in
as case #1 **without re-running**, carrying non-claims, and transporting human-authored
labels.

## In-scope

- New `corpus` subcommand (`src/plumb/cli/`), shell-level named causes, usage/exit contract
  in the `verify` subcommand style (`src/plumb/cli/__init__.py:144-265`).
- Record validation via the replay chain: `parse_trace` (run-id check) + `Capture` rebuild
  from `objects/` + `verify_claims` re-derivation; bank **refuses** (named cause) on any
  mismatch with the record's committed `verdicts.json` (the `_cross_check` precedent,
  `src/plumb/cli/replay.py:172-180`).
- Non-claim lane: `nonclaims.json` (records + named causes — AgroDesign's
  `unrepresentable.json`) banks into the case; counts in coverage denominators, never in
  verdict precision (R4).
- Label transport: a human-authored review (case #1: the owner's committed DIVERGED review,
  `fixtures/gate/agrodesign/README.md:75-82`) may seed `labels.json`; the bank **transports,
  never creates** a label value — no human-authored review → no `labels.json` written.
- Case #1 acceptance: banking `fixtures/gate/agrodesign/` round-trips byte-identically and
  re-derives 85 `REPRODUCED` / 1 `DIVERGED` from its own stored trace.

## Out-of-scope

- Store format, case_id, append-only semantics (store aspect).
- Benchmark math / report (benchmark aspect).
- Label editing surface beyond transport; third-party labels.

## Acceptance criteria (tests written first)

1. `plumb corpus bank fixtures/gate/agrodesign --store <tmp>` writes a case whose members
   round-trip byte-identically to the record's committed bytes (including `verdicts.json`).
2. The banked case re-derives its verdicts from its own stored trace (parse_trace + Capture
   rebuild + verify_claims) — 85 `REPRODUCED`, 1 `DIVERGED`, 0 `UNVERIFIED` — and the
   re-derivation matches the banked `verdicts.json` exactly.
3. A record whose committed `verdicts.json` disagrees with re-derivation is refused with a
   named cause; nothing is banked.
4. Non-claims bank with their named causes (2× `p ¡ 0.001` from `unrepresentable.json`);
   they appear in the case and never in verdict precision.
5. Case #1's `labels.json` carries `confirmed` for the DIVERGED claim_id, sourced from the
   owner's review; a record with no human-authored review banks with **no** `labels.json`
   (guard-mutation-checked: the engine never invents a label value).
6. Exit contract: 0 on banked/no-op, 1 on any refusal (named cause), 2 on usage; never a
   traceback.
7. No network; full suite green under the autouse blocker.

## Dependencies & sequencing

- Requires the `store` aspect (`bank_case`, causes).
- Precedes `benchmark` (reads banked cases, incl. case #1's labels).

## Open questions / risks

- The `corpus` subcommand's parser needs a home in `build_parser`; keep the `verify` parser
  untouched (verify-cli PRD:180 left C5 writes out — the new subcommand is the surface).