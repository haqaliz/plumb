# Understanding — discrepancy-corpus (C5, first slice)

Source: `docs/planning/_card/issue.md` (pbf handoff brief, 2026-10-01). Dig agents mapped
`src/plumb/` (verify/run/cli/bundle seams) and the planning docs (C5 constraints) on
2026-10-01.

## What the work is really asking

Build C5's first slice — the **corpus store** — under `src/plumb/corpus/`:
every `(claim, re-derived value, verdict, locator, cause)` from a verify run banks as a
**self-contained, replayable, human-labelable case** under gitignored `corpus/local/`
(ARCHITECTURE.md:148-154), with canonical serialization, plus a bank command or seam that
folds the committed AgroDesign record in as **case #1 without re-running it**, and a
**benchmark scaffold** (precision/recall/coverage against human labels; `UNVERIFIED` excluded
from precision; engine never labels its own cases) that honestly reports the R1 coverage
number (ROADMAP.md:32-33, 68).

## Affected areas (mapped)

- **New package** `src/plumb/corpus/` (ARCHITECTURE.md:148). `corpus/local/` already gitignored
  (`.gitignore:20`).
- **Seams where the bank tuple is assembled:** `verify_claims` → `VerdictSet`
  (`src/plumb/verify/__init__.py:129-153`) — every `Verdict` already carries claim_id,
  reported_text, located_text, sha256, run_id, rederived, band/delta, locator, cause, verdict.
  CLI call sites: `_spine` (`src/plumb/cli/live.py:126-158`) and `replay_record`
  (`src/plumb/cli/replay.py:70-93`).
- **Reuse (no re-invention):** `serialize_verdicts` (`verify/serialize.py:40-47`),
  `parse_trace` (`run/trace.py:134-180` — validates the run id from its own bytes),
  `serialize_trace`, the `_JSON` options triplet (sort_keys, no whitespace, ensure_ascii=False,
  allow_nan=False), `Capture(store=objects, artifacts=…)` rebuild (the replay pattern,
  `cli/replay.py:118-121`), the cross-process PYTHONHASHSEED determinism harness
  (`tests/extract/test_determinism.py:320-366`), the no-network autouse guard
  (`tests/conftest.py:56-60`).
- **The record-directory is already the case shape:** `claims.json + bindings.json +
  trace.json + objects/ + verdicts.json` — a corpus case is that layout plus a stable case id
  and a label slot.
- **Case #1:** `fixtures/gate/agrodesign/` — 86 verdicts (85 REPRODUCED, 1 DIVERGED,
  0 UNVERIFIED), the DIVERGED already owner-reviewed (`review_required`, README:75-82) and
  drift-cross-checked (`drift.json`), `unrepresentable.json` holds 2 non-claims.

## Ambiguities / open questions (for the PRD)

1. **Precision/recall denominator semantics** — docs pin only "measured against human labels",
   "`UNVERIFIED` excluded from precision", headline "precision on `DIVERGED`". Per-claim vs
   per-case denominators, and how human labels define TP/FP for `DIVERGED` (confirmed vs
   refuted by review) are unspecified.
2. **Label schema & workflow** — who labels (owner), where labels live (docs hint: *beside*
   the case, not inside the engine's canonical verdict bytes — README:80-82), label states,
   third-party-validatable.
3. **Non-claim lane** — R3/claim-extraction/prd.md:103-105 demand non-claims with named
   causes never be silently dropped; AgroDesign's `unrepresentable.json` is the real example.
   The brief's tuple doesn't name it; decide whether the case format carries it.
4. **Case identity & store layout** — id scheme (record hash? run_id + paper hash?), one dir
   per case?, append-only semantics ("never mutates an existing case" → re-bank of the same
   record = no-op or error?).
5. **Bank surface** — new `plumb corpus` subcommand vs library seam; verify-cli PRD
   explicitly left C5 writes out (verify-cli/prd.md:180).
6. **What "without re-running" means mechanically** — bank imports the committed serialized
   bytes and *also* re-derives verdicts from the stored trace (per the acceptance tests:
   round-trip byte-identical **and** re-derive-from-trace), which is exactly the replay chain.

## Guardrail check (CLAUDE.md)

Execution-grounded only: labels are human, engine never labels its own cases (ARCHITECTURE
:152-154); no egress — `corpus/local/` is user-run-state, never leaves the box (R5, worktrees
skill:85-87); no bare LLM judge anywhere in the slice; `UNVERIFIED` never rendered as
`REPRODUCED`; a `DIVERGED` banks only with its full evidence chain and `review_required`.
No constraint conflicts found — the brief's case #1 (AgroDesign) is explicitly supported by
the docs (gate record is self-contained and replayable).