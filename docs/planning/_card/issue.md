# C4 Binding & verdict — issue card

Source: inline brief from the `plumb-next` handoff (no GitHub issue — slug id).
Capability text: `docs/technical/CAPABILITY_ROADMAP.md` C4; design:
`docs/technical/ARCHITECTURE.md` C4 (`src/plumb/verify/`); phase: `docs/ROADMAP.md` Phase 0
"C4 (minimum): bind one headline claim to a re-derived value and emit the verdict."

## Brief

Build the first C4 slice under `src/plumb/verify/`: deterministic locators (JSON pointer and
regex/stdout capture first; table-cell for CSV if cheap), a tolerance policy, and a per-claim
verdict (`REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`+cause) that reads
values only through C3's `RunTrace`/object store by hash, and compares on `ClaimValue`'s
`Decimal`, never its identity text. Caveat (R1): none of the five fixture papers' repos runs
offline (HRS/UK Biobank gated data), so acceptance runs on synthetic local repos through C3,
and choosing a real public gate paper is flagged as a separate, owner-authorized step. Settle
the open tolerance and locator-grammar questions from `ARCHITECTURE.md` in the PRD. Failing
tests first:

- An exact match gives `REPRODUCED`, and an in-band delta gives `WITHIN-TOLERANCE`.
- An out-of-band value from a fresh run gives `DIVERGED`.
- A value that fails to bind or binds twice gives `UNVERIFIED: NO_BINDING` /
  `AMBIGUOUS_BINDING`.
- A claim with no tolerance gives `NO_TOLERANCE`.
- Every C3 failure cause (`STALE_ARTIFACT`, `WONT_RUN`, `TIMEOUT`, `NO_ARTIFACT`,
  `ENTRYPOINT_*`) passes through as `UNVERIFIED` and never as `DIVERGED` — a load-bearing
  false-`DIVERGED` guard with a mutation check.
- The verdict records are byte-identical across processes.
