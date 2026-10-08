# spine — aspect spec (`notebook-capture`)

Problem slice: PRD M7–M9 + S1. Prove the notebook path end-to-end **without a real kernel in
tests**: a notebook-only repo resolves, the stub `jupyter` argv executes through the runner,
capture stores whole-file + cell artifacts under the deterministic run dir, verdicts follow
existing governance, and the trace/record/replay round-trips. Then update the public status
docs honestly.

## In scope

- CLI live e2e with a stub `jupyter` executable on PATH (`--no-env-build`): the stub rewrites
  `analysis.ipynb` in the working copy with executed outputs and prints the claimed value;
  capture stores the `notebook` and `notebook_cell` objects in the run dir; a claim bound to
  `<stdout>` decides `REPRODUCED` (no `notebook_cell` locator exists yet — that is the next
  unit; the notebook objects are still captured and asserted).
- Trace/replay: `parse_trace(serialize_trace(trace))` is the identity for a run carrying
  notebook artifacts; a notebook run written with `write_record` replays through
  `plumb verify --from-record` byte-identically against the record's `verdicts.json`, with
  `objects/` carrying only locatable artifacts (whole notebook + cells).
- Docs (M9): `docs/technical/CAPABILITY_ROADMAP.md` (C3 status),
  `docs/technical/ARCHITECTURE.md` (C3 status), `CLAUDE.md` (C3 sentence), `README.md`
  (Built / Not built rows, and the stale test-count line) — all honest: capture built,
  `notebook_cell` locator not built, R1 not moved.
- `src/plumb/run/__init__.py` docstring: the "named follow-on" sentence becomes status,
  without touching the pinned cause table.
- S1 dev-time evidence: `tools/notebook_probe.py` runs a synthetic notebook repo through the
  CLI with a real `uv` env carrying jupyter/nbconvert/ipykernel; its output is recorded as
  committed evidence; never in tests or CI.

## Out of scope

- The C4 `notebook_cell` locator and any binding-schema change.
- New CLI flags; capture/entrypoint behavior changes (if a test exposes a real gap, fix it
  minimally and test-first, and say so).
- Real kernel execution in tests/CI.

## Acceptance criteria (testable, written failing first — tests offline)

1. **CLI live e2e.** Notebook-only repo + stub `jupyter` on PATH + a paper claim bound to
   `<stdout>` → exit 0; the deterministic run dir under the patched work root contains the
   stub notebook's exact bytes and the canonical cell projection among its objects; `--json`
   shows the claim decided.
2. **Replay.** A recorded notebook run replays via `plumb verify --from-record` → exit 0 and
   `--json` byte-identical to the record's `verdicts.json`; the trace round-trip is the
   identity over notebook artifacts.
3. **Determinism.** Two CLI invocations on the same notebook inputs produce byte-identical
   stdout and reuse one deterministic run dir (existing pattern).
4. Full suite green, network-free; production behavior changes are docs-only unless a real
   gap is found and fixed test-first.
5. Docs updated and honest; the README test-count line refreshed to the actual green count.
6. Dev-time: the probe runs on this machine and its output is committed as evidence (not a
   test).

## Dependencies and sequencing

After `entrypoint` (b710114, 03886cc) and `capture` (dc0781c, d94083d). S1 (trace/replay) →
S2 (CLI e2e) → S3 (docs + dev evidence).

## Open questions / risks

- A real `jupyter` env on this machine for S1 evidence may not build offline; the probe is
  should-have and reports honestly either way.
- The stub script must be executable and mimic nbconvert's exit behavior (nonzero → `WONT_RUN`
  is already covered by the runner; the e2e uses the success path).
