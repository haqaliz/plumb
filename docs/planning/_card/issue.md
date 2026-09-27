# plumb verify CLI — issue card

Source: inline brief from the `plumb-next` handoff (no GitHub issue — slug id). Capability:
`docs/technical/CAPABILITY_ROADMAP.md` C4 (hardening slice) + C6; origin: Phase 1 of
`docs/ROADMAP.md` ("Ship the self-hostable CLI: C1–C4 hardened + C6 (signed replayable bundle)
— `plumb verify <paper> <repo>` returns a per-claim verdict table and a bundle"); shape target:
`docs/technical/ARCHITECTURE.md` CLI section.

## Brief

Build the plumb verify CLI (Phase 1 headline per docs/ROADMAP.md:37-39; shape already specced
in docs/technical/ARCHITECTURE.md:189): `plumb verify <paper> <repo> [--rev REV] [--out bundle/]`
runs the C1→C2→C3→C4→C6 spine and prints a per-claim verdict table plus UNVERIFIED-with-cause,
writing a signed bundle. Test-first, offline: acceptance tests replay the committed AgroDesign
trace/objects for byte-identical 85 REPRODUCED / 1 DIVERGED and a bundle that verify_bundle
accepts (signature checked first); a failing repo yields non-zero exit with named UNVERIFIED
causes, never DIVERGED; two invocations on the same input are byte-identical; the real AgroDesign
run is a dev-time demo, never CI. Caveat (R1): the end-to-end path has run on one paper via
library calls only — bind the CLI to the existing seam (`plumb.verify.verify_claims`,
`plumb.bundle.build_bundle`) and keep every existing guard green.