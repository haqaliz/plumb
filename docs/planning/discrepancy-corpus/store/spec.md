# Spec — discrepancy-corpus / store

Source: `docs/planning/discrepancy-corpus/prd.md` requirements R1, R2 (plus the
determinism contract). Date: 2026-10-01.

## Problem slice

The corpus store foundation: a case format and store under gitignored `corpus/local/` such
that every verify run's `(claim, re-derived value, verdict, locator, cause)` banks as one
**self-contained, replayable, append-only** case whose bytes are canonical and whose
identity is content-addressed.

## In-scope

- Case directory layout: `case.json` (manifest) + the record's member bytes (`claims.json`,
  `bindings.json`, `trace.json`, `verdicts.json`, `objects/`, optional `nonclaims.json`,
  optional `labels.json` slot).
- `case_id` derivation: SHA-256 over canonical member hashes in pinned order (paper hash,
  run_id, member SHA-256s, objects-tree hash) — same style as `derive_run_id`
  (`src/plumb/run/trace.py:69-75`).
- `case.json` manifest: format `plumb-corpus-case/1`, case_id, paper hash, run_id, member
  hashes, objects-tree hash, labels presence flag. Canonical JSON (house `_JSON` options:
  sorted keys, no incidental whitespace, `ensure_ascii=False`, `allow_nan=False`, one
  trailing newline). **No timestamps, no absolute paths** — byte-identical across processes.
- Store semantics: bank = write-once. Re-bank of an identical case → **no-op** (same
  case_id returned, nothing written). Same case_id, different bytes → **refused** with a
  named cause, existing case untouched. Read-back verifies every member hash; a mismatch is
  a named cause, never silently accepted.
- Public seam in `src/plumb/corpus/`: `bank_case(...)`, `read_case(...)`, `derive_case_id`,
  closed cause vocabulary in the house style (`plumb.verify.causes` precedent).

## Out-of-scope

- The `plumb corpus` CLI (bank aspect).
- Replay-chain validation / re-derivation from the stored trace (bank aspect).
- AgroDesign folding, non-claims, label transport (bank aspect).
- Benchmark math and report (benchmark aspect).

## Acceptance criteria (tests written first)

1. `case_id` is deterministic: identical record bytes → identical case_id across processes
   and `PYTHONHASHSEED` values; any member differing → different case_id.
2. Round-trip: `bank_case` → `read_case` → every member byte-for-byte identical.
3. Re-bank of an identical record is a no-op: same case_id, no files rewritten, case bytes
   unchanged.
4. Same case_id with different member bytes → refused (`CASE_CONFLICT`), existing case
   untouched (mutation-checked).
5. A tampered stored member → read refuses with a named cause (`CASE_TAMPERED`), never
   returns forged bytes.
6. Manifest/case bytes are canonical: cross-process identity, no timestamps, no absolute
   paths (schema + source guards in the `tests/extract/test_determinism.py` style).
7. Objects-tree hash is deterministic over the sorted object set.
8. Full suite passes under the autouse no-network blocker (`tests/conftest.py:56-60`).

## Dependencies & sequencing

- Depends on C4's serialized bytes only (`serialize_verdicts`, `serialize_trace` formats are
  read, never re-spelled). No new runtime dependency.
- Precedes `bank` (which calls `bank_case` with record members) and `benchmark` (which reads
  cases).

## Open questions / risks

- None blocking. Object-tree hash framing (sorted list vs plumb bytes framing) is a
  low-stakes choice; pick the canonical-JSON-of-sorted-hashes form unless the intake
  framing is trivially reusable.