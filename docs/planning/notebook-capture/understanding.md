# Understanding — notebook-capture (C3 follow-on)

Date: 2026-10-08. Source: `docs/planning/_card/issue.md` (no GitHub issue). Deep-dig inputs:
code map of `src/plumb/run/` + `src/plumb/cli/` + `src/plumb/verify/` and the design docs.

## What the work is really asking

C3's named follow-on: **notebook entry-point resolution + cell-output capture**. A repo whose
only entry is an executed `analysis.ipynb` (the survey's dominant failure mode — "the table is
computed in `analysis.ipynb` from a pickle", `docs/planning/gate-paper/survey.md:47-48`;
`screening.md:46,60-62`) must resolve, run, and have each cell's outputs content-addressed into
the per-run object store. It is the first-listed engine gap blocking panel growth
(`docs/planning/cross-paper-coverage/panel-run/screening.md:295-298`;
`docs/technical/CAPABILITY_ROADMAP.md:238-241`) and R1's named mitigation ("notebook cell",
`docs/ROADMAP.md:90`).

C3 emits **no verdicts** (`src/plumb/run/__init__.py:8-11`): it supplies evidence and named
causes. The coupled C4 notebook-cell locator is a follow-on (`docs/planning/binding-verdict/prd.md:238`);
capture without it does not move R1's number — this unit's scope boundary is a PRD decision.

## Affected areas (built code)

- `src/plumb/run/entrypoint.py:40-71` — discovery today: explicit wins; else exactly one of a
  single `[project.scripts]` entry or a root `main.py`; none/many are named causes. No
  notebook rule. Root-only scanning doctrine (`src/plumb/intake/manifest.py:5-7`).
- `src/plumb/run/capture.py:44,97-142` — capture walks only `.json`/`.csv` plus stdout/stderr;
  freshness guard is per-file, strict `<` run start, bytes never read for stale
  (`capture.py:114-122`); `Capture.read` re-hashes and is the only read path
  (`capture.py:87-94`). `.ipynb` is not captured at all today.
- `src/plumb/run/trace.py:50-99` — `RunTrace` + canonical serialization; `derive_run_id`
  hashes argv + tree hash + sorted locatable artifact hashes (`trace.py:69-75`); artifacts are
  generic records `(kind, relpath, sha256, size, mtime_ns, diagnostic_only)`
  (`capture.py:50-59`) — new artifact kinds need no schema change.
- `src/plumb/run/runner.py:80-150` — executes an `EntryPoint.argv` in a working copy under the
  run area, mtimes preserved, scrubbed env + `.venv` on PATH (`runner.py:171-179`); OSError →
  `WONT_RUN`, timeout kills the process group.
- `src/plumb/cli/live.py:154-198` — live spine calls `resolve_entrypoint` then
  `run_and_capture`; pre-run causes → all-`UNVERIFIED` via `NoRun.from_exception`.
- Ripple points for a new artifact kind / cause: bundle accepts only outputs in
  `trace.artifacts` locatable (`src/plumb/bundle/verify.py:215-225`), record copies locatable
  only (`src/plumb/cli/record.py:79-80`), cause vocabularies are pinned in four places
  (`run/causes.py`, `verify/causes.py`, `cli/__init__.py` `CLI_CAUSES`, `run/__init__.py`
  docstring + their tests).
- `pyproject.toml:7-9` — exactly one runtime dep (pypdf); no extras section.
- `src/plumb/intake/env.py:135-163` — the runner-seam precedent (stub in tests, real only via
  `tools/`), the model to follow for keeping kernels out of tests.

## Open questions for the PRD (and this unit's scope)

1. **Execution mechanism.** "needs nbconvert" (execution-capture PRD:33,108) is the only doc
   statement: which tool, run from which interpreter — the checkout's env (`jupyter` on the
   runner's PATH, `runner.py:171-179`) or a new pinned Plumb runtime dep? No doc decides.
2. **Capture granularity.** Per-cell artifacts (the card's wording, `issue.md:35-36`) vs one
   whole-notebook artifact whose cells the future locator parses. Per-cell fits the artifact
   model with no trace-schema change; addressing must be deterministic and path-free.
3. **Discovery semantics.** Root-only `*.ipynb` (house doctrine) and precedence versus
   `[project.scripts]`/`main.py`: strict equal-ranking would make `main.py` + an exploratory
   notebook `ENTRYPOINT_AMBIGUOUS`. Fallback rule vs equal candidate?
4. **Scope: capture-only vs capture + C4 locator.** The card defers the locator; R1's number
   only moves with both.
5. **Named cause for a missing notebook tool** (`jupyter` not in the checkout env) — reuse
   `WONT_RUN` (OSError path) or add a new cause (four-vocabulary ripple).
6. **Tool-version recording** (the card's "recorded as C2 records its tools"): trace argv only
   for now, or an env-descriptor field, or a RunTrace schema change (parse_trace is strict).

## Contradictions surfaced

- `docs/planning/execution-capture/prd.md:93` says "No new runtime deps", while the named
  follow-on says "needs nbconvert" (`prd.md:108`) — unresolved; the PRD must settle it.
- `docs/planning/_card/understanding.md` is stale (a 2026-09-27 note on C1 claim recovery);
  this note supersedes it for this unit.
- `README.md:24` still lists "other value kinds · corpus" as not built — stale status drift,
  not to be propagated.
- R1's mitigation names a notebook-cell *locator* (`ROADMAP.md:90`) while C4's spec excludes it
  (`binding-verdict/prd.md:238`) — capture alone will not move the number.

## Guardrails

Execution decides (no verdicts here); freshness guard is load-bearing (a committed notebook is
never parsed — constraint #5); tests stay offline with synthetic `.ipynb` fixtures and never
run a real kernel (the conftest blocker cannot stop subprocesses, `tests/conftest.py:14-19`);
the pinned checkout is never touched; no absolute run-side paths in the trace; R1 stays honest
(unseeded notebooks still end `UNVERIFIED`).
