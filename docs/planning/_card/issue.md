# C3 Execution & result capture — issue card

Source: inline brief from the repo's own roadmap and design docs (no GitHub issue — slug id).
Capability text: `docs/technical/CAPABILITY_ROADMAP.md` C3 (lines 62-70); design:
`docs/technical/ARCHITECTURE.md` C3 (lines 84-91); phase: `docs/ROADMAP.md` Phase 0 "C3
(minimum): run the repo's own entry point and capture structured output, freshness-guarded."

## Brief

**C3 — Execution & result capture.** Run the repo's own entry point(s) and capture structured
outputs — JSON, CSV, stdout — **content-addressed** and **freshness-guarded** (an output file
whose mtime/provenance predates this run is never read as a fresh result). Why: the
re-derived value must come from an actual run, not a committed artifact (constraint #5).
Depends on C2 (the checkout + env descriptor from `src/plumb/intake/`); C2 is complete on the
`artifact-intake` branch. Guardrail: failure to build, run, or time out is captured with a
named cause, never silently dropped. Tests stay offline: entry points are local scripts,
outputs are produced in tmp run areas, and the freshness guard is exercised by back-dating
an output file's mtime (subprocess is legal in tests; sockets are not). Notebook cell output
capture is deferred to a later slice (needs nbconvert). The Phase 0 gate's C3 minimum is the
acceptance bar: run the repo's own entry point and capture structured output,
freshness-guarded.