# C6 Signed bundle — understanding (deep dig, 2026-09-27)

## What the work is really asking

The last missing piece of the Phase 0 gate: "at least one real, reproducible `DIVERGED` (or a
clean panel of `REPRODUCED`) with a **bundle a third party can replay**" (`docs/ROADMAP.md`).
The real-paper panel exists (`fixtures/gate/agrodesign/`: 86 bound, 85 `REPRODUCED`,
1 `DIVERGED`). C6 turns it into a portable, signed, independently checkable record.

Two levels of replay, which must not be confused:

1. **Verdict replay (offline):** from the bundle alone, re-check every member's hash and the
   signature, then re-derive the verdicts from the captured outputs and compare byte for byte.
   Anyone can do this with no network and no environment.
2. **Run replay (networked, opt-in):** re-clone the repo at the pinned rev, check the tree hash,
   install the frozen environment, re-run the recorded argv, and compare the fresh outputs'
   hashes to the bundle's. This is what shows the numbers came from that code.

## What exists to build on (verified)

- `serialize_claims(claims, paper_hash=...)` (C1) — canonical claims + the paper hash; there
  is **no loader**, so C6 needs `parse_claims` (6 value variants + `CharSpan`; the id must
  recompute).
- `serialize_trace` / `parse_trace` (C3, `parse_trace` added for the gate record; re-checks the
  run id). `RunTrace` holds the tree hash but **not** the source URL/rev — those live on
  `Checkout.source` (`SourceRecord`: kind, location, rev_requested, rev_resolved), which the
  gate run did not persist. AgroDesign's: `https://github.com/DeepStatistix/AgroDesign.git`,
  `v1.0.1` → `18b7c29a4f8de3dc9260b9fa42849e5a74097825`.
- `load_bindings`, `verify_claims`, `serialize_verdicts` (C4). `verify_claims` reads bytes only
  for **bound** artifacts; the run-id check uses the trace's artifact hashes, not bytes. So a
  bundle can carry only the objects the bindings read — minimal disclosure (constraint #2).
- `environment.txt` in the gate record: `python==3.12.13` + a `uv pip freeze`.

## Signing spike (scratchpad, throwaway key)

OpenSSH 10.2 here; `ssh-keygen -Y sign/verify` exists since OpenSSH 8.1. Ed25519 SSHSIG over a
file: **deterministic** (two signatures byte-identical), tampered content fails (rc 255), a
wrong namespace fails, `-Y check-novalidate` checks without a trust root. No Python dependency.

## Open questions (for the PRD)

1. Signing scheme — spike favours `ssh-keygen -Y`.
2. Whose key signs the committed AgroDesign bundle — an owner decision; never the owner's
   personal key without asking.
3. Is the paper PDF a member? It is public and identified by hash; including it by default
   would make the bundle carry raw paper bytes.
4. What "gate met" requires once the bundle exists.
