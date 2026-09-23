# PRD — C3 execution & result capture (slug: `execution-capture`)

## Problem Statement

The Phase 0 gate's C3 minimum is "run the repo's own entry point and capture structured
output, freshness-guarded" (`docs/ROADMAP.md:23`). The re-derived value in the whole wedge
must come from an actual run — never from a committed artifact (constraint #5;
`CAPABILITY_ROADMAP.md:62-70`). C2's checkout + env descriptor exist; C3 is what turns them
into a **RunTrace**: what ran, what it produced (content-addressed), and the freshness guard
that makes a stale output `STALE_ARTIFACT` instead of data.

## Goals & Success Metrics

Run the repo's own entry point under the recorded environment; capture stdout + JSON/CSV
outputs, each content-addressed; every artifact carries provenance; a stale artifact is
never parsed. Failures resolve to named causes. The C4 binder (next unit) consumes
`RunTrace` artifacts.

### Acceptance criteria (test-first)

1. An entry point resolves and runs under the checkout's env posture (subprocess, cwd =
   checkout, scrubbed env, timeout); the exact argv, cwd, and exit code are recorded.
2. stdout and any `.json`/`.csv` the run writes under the run area are captured and
   content-addressed (sha256) in the trace.
3. **Freshness guard (load-bearing):** an output file whose mtime predates the run start
   yields `STALE_ARTIFACT` and is never parsed — tested by back-dating a file's mtime.
   A committed output in the checkout is never captured (it isn't written by this run).
4. Failures: entry point missing → `ENTRYPOINT_MISSING`; ambiguous → `ENTRYPOINT_AMBIGUOUS`;
   process fails → `WONT_RUN` (with exit code); timeout → `TIMEOUT`; env build failure →
   `ENV_BUILD_FAILED` (from C2). Never silent.
5. No network in any test; no new runtime deps; determinism suite stays green; full suite
   green.
6. Notebook cell capture is out of scope, named as a follow-on (needs nbconvert).

## User Personas & Scenarios

- **The gate:** `plumb verify`'s run side — the paper's repo runs on the user's compute and
  produces captured, freshness-guarded outputs.
- **The binder (C4):** consumes `RunTrace` to aim locators at content-addressed artifacts.
- **A researcher:** sees exactly what ran (argv, env policy, tree hash) — the trace is the
  "what actually happened" record C6 will bundle.

## Requirements

### Must-have

- **M1. Entry-point resolution.** `resolve_entrypoint(checkout, manifest_scan, explicit=None)`
  → recorded argv. Explicit wins; else discovery (pyproject script group → `uv run <name>`;
  `main.py` → `python main.py`); ambiguity → `ENTRYPOINT_AMBIGUOUS`; none → `ENTRYPOINT_MISSING`.
- **M2. Runner.** `run_entrypoint(checkout, env_build, argv, *, timeout)` → subprocess under
  C2's posture; captures stdout/stderr bytes + exit code; `WONT_RUN` / `TIMEOUT` with named
  causes; a run-area dir is created (scratch, not the checkout) and recorded.
- **M3. Capture & content addressing.** `capture_outputs(run_dir, run_started_at)` — every
  `.json`/`.csv` written by the run, hashed (sha256); stdout hashed; provenance per artifact
  (relpath, mtime, hash, bytes). Deterministic record.
- **M4. Freshness guard.** An artifact with `mtime < run_started_at` is recorded as
  `STALE_ARTIFACT` and excluded from parsable outputs — with a load-bearing test that
  back-dates a file and asserts it is never parsed. Staleness is strict `<` (a same-second
  file is fresh — boundary test); a run that preserves an old mtime (`cp -p`) is detected as
  stale by this guard. Exit 0 with zero artifacts and empty stdout is a **successful run
  with a `NO_ARTIFACT` named cause** (a binding problem for C4, not a run failure).
- **M5. RunTrace record.** `RunTrace(run_id, argv, cwd, env_policy, tree_hash, exit_code,
  artifacts, failures)` — deterministic serialization (no absolute paths; relpaths + hashes),
  ready for C6 bundling.
- **M6. Docs.** `CAPABILITY_ROADMAP.md` C3 status; `README.md`/`CLAUDE.md` rows; honest
  "gate still not met" (C4 unbuilt).

### Should-have

- **S1.** `stderr` captured alongside stdout — diagnostic-only, **never a locator target**
  in the first slice (C4 regex locators target stdout/JSON/CSV only).
- **S2.** Run-id derivation is deterministic — input order pinned: sha256 over
  `argv + tree_hash + sorted artifact hashes`, so identical inputs produce identical ids
  (C6 replay compares traces).

### Nice-to-have

- **N1.** A `--timeout` override recorded in the trace.

## Technical Considerations

- **Capability:** C3 (`CAPABILITY_ROADMAP.md:62-70`); depends on C2 (done on the parent
  branch). C4 depends on this.
- **Package:** `src/plumb/run/` — outside extract/ AST-guard scope; `os`, `pathlib`, `time`,
  `subprocess`, `hashlib` allowed; own no-network + determinism tests.
- **Run area:** scratch dir under the recorded run area (`.gitignore`d), never the checkout —
  committed outputs can't be captured by accident (that is the freshness guard's point).
- **Determinism:** artifact hashes are content hashes; RunTrace serialization uses relpaths
  only and a fixed field order.
- **Verdict impact:** C3 emits no verdicts; its named causes are the future `UNVERIFIED`
  input (`STALE_ARTIFACT` is already a reserved cause in ARCHITECTURE.md's closed
  vocabulary). DIVERGED can never come from a stale or harness-side failure.
- **No new runtime deps.**

## Risks & Open Questions

- **R1 (binding coverage):** this is the mitigation's second half — repos that won't run now
  produce `WONT_RUN`/`TIMEOUT` named causes instead of silence. The honest number (fraction
  that run) becomes measurable at the gate.
- **R2 (false DIVERGED):** the freshness guard is R2's first line — a stale value can never
  be compared, let alone DIVERGED.
- **Open:** whether stdout is a "structured output" for locators in the first slice (regex
  locators in C4 will target stdout) — record it as a capturable artifact (yes).
- **Open:** resource caps beyond timeout (memory/disk) — recorded, enforcement follow-on.

## Out of Scope

- Notebook cell capture (follow-on, needs nbconvert), entry-point *inference* beyond the
  two discovery rules, resource-cap enforcement, any verdict emission, C6 bundling.

## Proposed Aspect Decomposition

1. `runner` — entry-point resolution (M1) + subprocess runner with named causes (M2).
2. `capture` — artifact discovery, content addressing, provenance (M3) + the freshness
   guard (M4, load-bearing test).
3. `trace` — `RunTrace` record + deterministic serialization (M5), API wiring, docs (M6).

Sequencing: `runner` → `capture` → `trace`.