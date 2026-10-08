# PRD — C3 notebook capture (slug: `notebook-capture`)

## Problem Statement

C3's named follow-on. `resolve_entrypoint` knows two discovery rules — a single
`[project.scripts]` entry or a root `main.py` (`src/plumb/run/entrypoint.py:6-16,52-71`) — and
capture walks only `.json`/`.csv` plus stdout/stderr (`src/plumb/run/capture.py:44,134-142`).
A repo whose only entry is an executed `analysis.ipynb` is therefore unreachable: it ends
`ENTRYPOINT_MISSING` or `NO_ARTIFACT`.

This is the first-listed engine gap blocking panel/corpus growth — *"Growing the corpus is
blocked by named engine gaps, in order: notebook-cell capture (C3), a poetry env policy (C2),
and figure-with-data locators"* (`docs/planning/cross-paper-coverage/panel-run/screening.md:295-298`;
`docs/technical/CAPABILITY_ROADMAP.md:238-241`) — and "notebook cell" is R1's named
mitigation (`docs/ROADMAP.md:90`). Notebook-rendered results are the dominant failure mode in
both selection passes: the ReScience catalogue ("the table is computed in `analysis.ipynb`
from a pickle", `docs/planning/gate-paper/survey.md:47-48`) and the wider panel
(`screening.md:46,60-62,292-294`). The named follow-on: "Notebook cell capture (follow-on,
needs nbconvert)" (`docs/planning/execution-capture/prd.md:108`;
`docs/technical/ARCHITECTURE.md:109`).

C3 emits **no verdicts** (`src/plumb/run/__init__.py:8-11`): it supplies evidence and named
causes. The coupled C4 `notebook_cell` locator is the immediately-next unit
(`docs/planning/binding-verdict/prd.md:238`); capture alone does **not** move R1's number, and
this PRD does not claim it does.

## Goals & Success Metrics

A repo whose only entry is a root notebook resolves to a notebook entry, executes in the
working copy under the recorded env posture, and has the notebook captured — whole file plus
per-output cell artifacts — content-addressed and freshness-guarded, with the `RunTrace`
schema unchanged. The (next-unit) locator can then address `<relpath>#cell-<i>` without
re-capturing.

Outcome note: this unit's metric is capability + an offline e2e (below). R1's number moves
only when the C4 `notebook_cell` locator lands; that unit's metric is a real notebook paper
resolved → captured → bound → decided, banked as a case.

### Acceptance criteria (test-first)

1. **Resolution.** With no `[project.scripts]` entry and no root `main.py`, exactly one root
   `*.ipynb` resolves to `EntryPoint(argv=("jupyter","nbconvert","--to","notebook",
   "--execute","--inplace","<relpath>"), source="notebook")`. Several root notebooks →
   `ENTRYPOINT_AMBIGUOUS`; none in any rule → `ENTRYPOINT_MISSING`. Never a guess.
2. **Capture.** A fresh executed `.ipynb` in a run's working copy yields one whole-file
   `notebook` artifact plus one `notebook_cell` artifact per cell whose `outputs` list is
   non-empty, addressed `<relpath>#cell-<i>` (0-based index into the `cells` array); every
   artifact is readable only by hash through `Capture.read`.
3. **Freshness (load-bearing).** A committed (untouched) notebook — mtime before run start,
   strict `<` — is `STALE_ARTIFACT`: one `StaleOutput` for the file, its bytes never read,
   zero cell artifacts. A committed notebook the run rewrites is fresh.
4. **Determinism.** The `RunTrace` is byte-identical across processes under varied
   `PYTHONHASHSEED`, carries no absolute paths, and needs no schema change (artifacts are the
   existing generic records); `parse_trace` round-trips a notebook trace and replays it.
5. **Causes.** A missing `jupyter` tool or a failing execution is `WONT_RUN` (with detail /
   exit code), a hang is `TIMEOUT`; no new cause is added to any closed vocabulary. A
   successful run that captured no notebook and no other output is `NO_ARTIFACT`.
6. **Offline.** The full suite stays green and network-free: no test invokes a real kernel or
   `nbconvert` (a synthetic `jupyter` stub on PATH exercises the live CLI path end-to-end);
   no real kernel runs in CI.
7. **No new runtime deps.** `pyproject.toml`'s runtime dependency set is unchanged; the
   notebook tool is a property of the *checkout's* environment.
8. **Docs.** `CAPABILITY_ROADMAP.md` (C3), `ARCHITECTURE.md` (C3), and `CLAUDE.md` status
   paragraphs updated honestly: capture built, locator not built, R1 not moved.

## User Personas & Scenarios

- **The panel campaign (R1):** a notebook-driven paper whose results table lives in
  `analysis.ipynb` becomes runnable and capturable — the precondition for banking it.
- **The binder (C4, next unit):** aims a `notebook_cell` locator at
  `<relpath>#cell-<i>`; the artifact bytes are the canonical `outputs` array, addressed from
  the same store — never a re-read of the working copy.
- **A researcher replaying:** the trace records exactly what ran (argv, notebook relpath,
  source `"notebook"`, env policy) without a new schema.

## Requirements

### Must-have

- **M1. Root notebook scan.** `ManifestScan` gains `notebooks: tuple[Path, ...]` — root-level
  `*.ipynb` files, sorted, mirroring the existing root-only scan doctrine
  (`src/plumb/intake/manifest.py:5-7,35-51`). No recursion.
- **M2. Fallback discovery rule.** In `resolve_entrypoint`, notebooks are considered **only
  when the existing rules yield no candidate** (no scripts entry and no root `main.py`).
  Exactly one → `EntryPoint(..., source="notebook")` with argv
  `("jupyter","nbconvert","--to","notebook","--execute","--inplace","<relpath>")`;
  more than one → `EntryPointAmbiguous`; zero → `EntryPointMissing` (existing). Precedence is
  recorded, never guessed.
- **M3. Execution through the existing runner.** No new runner seam: the argv runs through
  `run_entrypoint` in the working copy with the existing posture (`runner.py:80-150`), so the
  checkout `.venv`'s `bin` is on PATH (`runner.py:171-179`) and its `jupyter` is used. Missing
  tool → `WONT_RUN` (the OSError path, `runner.py:130-133`); nonzero exit → `WONT_RUN`;
  timeout → `TIMEOUT`. No kernel invocation in tests.
- **M4. Whole-file notebook artifact.** Every fresh `.ipynb` under the working copy
  (recursive, like `.json`/`.csv` capture — **file-driven**: any notebook this run leaves
  fresh, whether or not Plumb chose it as the entry point) is stored as one artifact,
  `kind="notebook"`, `relpath` the file's POSIX relpath, `sha256` over the raw file bytes,
  with mtime and size. Storing the whole file means bytes are preserved even when the JSON
  cannot be decomposed; an **undecomposable** fresh notebook yields the whole-file artifact
  and zero cell artifacts, with no new cause and no silent drop. Undecomposable covers a
  malformed/non-JSON file, a missing/non-list `cells`, and any cell output the canonical
  projection cannot serialize (e.g. a `NaN`/`Infinity` literal).
- **M5. Per-cell artifacts.** For each fresh parseable notebook, every cell whose `outputs`
  is a non-empty list produces one artifact, `kind="notebook_cell"`, `relpath`
  `<notebook-relpath>#cell-<i>` (0-based index into the `cells` array), `sha256` over the
  canonical projection of that cell's `outputs` array — sorted keys, compact separators,
  UTF-8, one trailing newline, matching the house canonical form (`src/plumb/run/trace.py:42-47,97-99`).
  Markdown/raw cells and cells with empty outputs contribute nothing.
- **M6. Freshness guard applies to the notebook file.** Strict `<` run start; a stale notebook
  is one `StaleOutput` (relpath, mtime, size) whose bytes are never read — no file artifact,
  no cell artifacts, no parse. A run that rewrites the notebook makes it fresh. The boundary
  test (mtime == start is fresh) extends to notebooks.
- **M7. Trace and replay unchanged.** No `RunTrace` schema change: notebook and cell artifacts
  are ordinary `Artifact` records; `derive_run_id` (`trace.py:69-75`) and `parse_trace`
  (`trace.py:134-180`) work as-is; no absolute paths; ordering deterministic via the existing
  `(kind, relpath)` sort. `plumb verify --from-record` replays a notebook record byte-identically.
- **M8. CLI surface unchanged; offline e2e.** No new flags. A synthetic repo plus a stub
  `jupyter` executable on PATH exercises the live `plumb verify` path end-to-end; the stub
  writes an executed notebook and the CLI reports verdicts per existing governance
  (run-level causes → all `UNVERIFIED`).
- **M9. Docs.** Update `docs/technical/CAPABILITY_ROADMAP.md` (C3 status),
  `docs/technical/ARCHITECTURE.md` (C3 status), `CLAUDE.md` (the C3 status sentence), and
  `README.md`'s notebook row if it carries one — all honest about capture-built /
  locator-not-built.

### Should-have

- **S1. Dev-time real evidence.** One real run at dev time — a synthetic notebook repo with a
  real `uv` env carrying `jupyter`/`ipykernel`, executed through the CLI — recorded as PR
  evidence in the `tools/demo_env_build.py` style (`tools/` only; never tests or CI).

### Nice-to-have

- **N1. Nested notebook discovery** (`notebooks/*.ipynb`) — named follow-on; root-only is the
  first slice.
- **N2. Notebook-tool provenance** — record the checkout env's `jupyter`/`nbconvert` version in
  the C2 env descriptor (not the trace schema) — follow-on.

## Technical Considerations

- **Capability:** C3 (`CAPABILITY_ROADMAP.md:68-89` naming in the roadmap doc; status in
  `src/plumb/run/__init__.py:33-35`). Depends on nothing new: C2 scan, C3 runner/capture/trace
  all shipped. C4's locator depends on this.
- **Affected modules:** `src/plumb/intake/manifest.py` (M1);
  `src/plumb/run/entrypoint.py` (M2, docstring rule list); `src/plumb/run/capture.py`
  (M4-M5, `_OUTPUT_KINDS` stays `.json`/`.csv`; `.ipynb` gets its own branch so it is never
  double-captured); `src/plumb/run/trace.py` unchanged (M7); `src/plumb/cli/live.py` unchanged
  (M8).
- **Artifact model:** `Artifact.kind`'s documented vocabulary (`capture.py:50-59`) gains
  `notebook` and `notebook_cell`; `Capture.locatable` keeps both bindable/bundleable
  (`src/plumb/bundle/verify.py:215-225` accepts any locatable trace artifact; `bound_objects`
  selects only what bindings read, `verify.py:256-259`).
- **Dependency stance:** no new runtime dep. `jupyter`/`nbconvert` live in the *checkout's*
  env, pinned by the env policy when declared, absent otherwise (`WONT_RUN`). This resolves
  the "No new runtime deps" vs "needs nbconvert" tension
  (`docs/planning/execution-capture/prd.md:93,108`) on the environment side, not Plumb's.
- **Determinism:** the cell projection excludes `execution_count` (a cell field, not an
  output) and never reorders outputs; identical notebooks produce identical artifact hashes.
  Unseeded notebook runs produce different outputs — honest, and the later C4/review layers
  handle it as they do today.
- **Verdict impact:** none. C3 emits no verdicts; every failure is a named cause that maps to
  `UNVERIFIED` under existing governance (`src/plumb/verify/__init__.py:141-162`). No path
  here can emit `DIVERGED`.
- **No egress; no network in tests:** `tests/conftest.py:14-19,56-60` cannot stop a
  subprocess, so the stub-`jupyter` pattern (not a real kernel) is the offline guarantee.

## Risks & Open Questions

- **R1 (High/High) does not move until the C4 locator lands** (`ROADMAP.md:90`;
  `binding-verdict/prd.md:238`). Accepted: this unit is the prerequisite, and the locator is
  the immediately-next slice.
- **Checkout envs without `jupyter`/`nbconvert` fail as `WONT_RUN`** — honest but narrows
  yield; the R1 number must reflect it. A repo whose notebook needs a kernelspec absent from
  its env fails the same way.
- **Bundles/records grow with cell count** (one artifact per output-bearing cell, plus the
  whole file). Accepted for the first slice; a size cap is a named follow-on, not silently
  introduced.
- **Open — explicit entry point at the CLI.** A repo with a root `main.py` *and* a working
  notebook resolves to `main.py` (fallback rule); if `main.py` fails, there is no CLI flag to
  redirect to the notebook (`resolve_entrypoint(explicit=...)` exists but is not surfaced).
  Candidate for the `--timeout-seconds`/`--run-dir` should-have slice.
- **Open — README drift.** `README.md:24` still lists value kinds/corpus as not built (stale
  since 2026-10-01/02). Not this unit's job; do not propagate it.
- **Open — unparseable notebook has no cause** (whole-file artifact only). Deliberate: bytes
  are preserved, nothing is dropped; if a policy need emerges, a capture-side refusal cause is
  its own unit.

## Out of Scope

- The C4 `notebook_cell` locator and any binding-schema change (`bindings.py`/`locate.py`/
  `serialize.py`) — the immediately-next unit.
- Nested notebook discovery (N1), R-language notebooks, papermill, container isolation,
  resource caps beyond the existing timeout.
- New CLI flags (`--entrypoint`, `--timeout-seconds`, `--run-dir`) and any C2 env-policy
  change (the poetry gap is a different unit).
- C7/C8.

## Proposed Aspect Decomposition

1. `entrypoint` — root notebook scan (M1) + fallback resolution and its causes (M2), with the
   docstring rule list updated.
2. `capture` — whole-file and per-cell artifacts, canonical cell projection, freshness guard
   extension, malformed-notebook handling (M4-M6).
3. `spine` — CLI e2e with the stub `jupyter`, replay round-trip, docs/status updates, dev-time
   real evidence (M7-M9, S1).

Sequencing: `entrypoint` → `capture` → `spine`.
