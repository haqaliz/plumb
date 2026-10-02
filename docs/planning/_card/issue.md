# Brief — cross-paper-coverage (C5, next slice)

Source: `pbf feat cross-paper-coverage` handoff from `plumb-next` (2026-10-02). No GitHub
issue exists for this work; the id lives in the branch and PR.

## Brief

Build C5's next slice test-first: **the R1 measurement** (cross-paper binding coverage,
`docs/ROADMAP.md:41-45, 68` — the last unmeasured High/High risk).

**First slice — `plumb verify --bank`:** the live spine persists its record dir
(`claims.json` + `bindings.json` + `trace.json` + `objects/` + `verdicts.json`, the replay
shape) and banks it through the existing `corpus bank` replay chain, no-op on re-bank
(N2, `docs/planning/discrepancy-corpus/prd.md:113-114`; the bank seam at
`src/plumb/cli/corpus.py` already validates by re-derivation). Today the live spine writes
no record dir — `--out` writes only the signed bundle (`src/plumb/cli/live.py:154-157`).

**Then the campaign:** run a small panel (3–5) of runnable Python/R data-analysis papers
through the live spine at dev time — a **fixed selection rule**, committed fixtures per the
AgroDesign precedent (`fixtures/gate/agrodesign/`) — bank each case, and publish the first
honest multi-paper coverage/precision/recall figure via `plumb corpus report`, every number
with its denominator and label-authority marker, updating R1's status in `docs/ROADMAP.md`.

**Caveat:** the number may be ugly (R1 High/High — most repos don't run or never expose the
headline number machine-readably). Report it honestly; `UNVERIFIED` is the honest default.
Real env builds stay dev-time-only (the `tools/demo_env_build.py` precedent,
`docs/technical/CAPABILITY_ROADMAP.md:109-111`), never in tests or CI. C1 recovery on new
papers is unmeasured — expect claim-recovery tuning per paper
(`docs/technical/CAPABILITY_ROADMAP.md:85-87`).

**Acceptance tests, written first:**
1. A synthetic live run with `--bank` writes a record that re-derives byte-identically and
   banks; re-bank is a no-op (append-only store, never mutates).
2. A second paper's committed record banks and re-derives from its stored trace matching
   its `verdicts.json`.
3. `plumb corpus report` pools ≥ 2 cases with per-case and pooled denominators and
   label-authority markers.
4. The suite stays network-free under the autouse blocker (`tests/conftest.py:56-60`);
   env builds never run in tests/CI.