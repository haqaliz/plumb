# C6 Signed replayable bundle — issue card

Source: inline brief from the `plumb-next` handoff (no GitHub issue — slug id). Capability:
`docs/technical/CAPABILITY_ROADMAP.md` C6; design: `docs/technical/ARCHITECTURE.md` C6
(`src/plumb/bundle/`); phase: `docs/ROADMAP.md` Phase 0 gate — "with a bundle a third party can
replay".

## Brief

Build C6's first slice under `src/plumb/bundle/`: a bundle binding the paper hash, the repo
tree hash + source (URL, rev), the environment freeze, the serialized trace, the captured
locatable outputs (by SHA-256) and the verdicts, signed with a detached signature, plus a
`verify_bundle` that re-checks every hash and the signature and re-derives the verdicts byte
for byte; and an opt-in run-level replay (re-clone at the pinned rev, install the frozen
environment, re-run). Settle the signing scheme in the PRD (`ssh-keygen -Y`, no new
dependency, vs a pinned crypto library). Caveat (R2): AgroDesign ships no lockfile, so replay
must use the frozen versions, and an output mismatch is `UNVERIFIED` with a cause, never
`DIVERGED`. Acceptance tests first: a bundle built from `fixtures/gate/agrodesign/` verifies
offline; a flipped byte in any member fails with a named cause; a wrong/missing signature
fails; a bundle carrying an absolute path or stderr is refused; re-derived verdicts are
byte-identical; the bundle is byte-identical across processes; the networked run-level replay
runs only from a `tools/` script, never in tests.
