# PRD — poetry-env-policy (C2 follow-on)

Unit: `feat poetry-env-policy` · Owner: aliz · Capability: **C2 — Artifact intake & pinned
environment** (`docs/technical/CAPABILITY_ROADMAP.md`) · Source brief:
`docs/planning/_card/issue.md` · Understanding: `docs/planning/poetry-env-policy/understanding.md`.

## Problem Statement

**For whom:** the engine itself, and anyone who trusts a `plumb verify` verdict on a
poetry-locked repo.

C2's environment descriptor recognises only `uv.lock` and `requirements*.txt`
(`src/plumb/intake/env.py:214-223`). A repo that ships a `poetry.lock` and nothing else falls
to the `"best-effort"` policy, whose command is a bare `uv sync` (`env.py:256-263`). Modern uv
no longer reads `[tool.poetry]` / `poetry.lock`, so that `uv sync` **exits 0 and leaves an
empty `.venv`** — recorded as `EnvBuild(ok=True)` (`env.py:158` trusts `build.ok`;
`run/runner.py:174` adopts any `checkout_dir/.venv` that `is_dir()`).

**Evidence it is real:** documented at `tools/perrin_gate_run.py:13-18`,
`fixtures/gate/perrin/README.md:88-90`, `docs/technical/CAPABILITY_ROADMAP.md:260-261`, and
`docs/planning/cross-paper-coverage/panel-run/screening.md:266-267,296-297`. It is the reason
Perrin had to be built through a bespoke dev-time runner at a drifted boundary
(`fixtures/gate/perrin/environment.txt:1`).

**Cost of the status quo:** a "built" environment with nothing installed is a **silent pass** —
forbidden by `CLAUDE.md` constraint #3 ("never a silent pass") and constraint #5 (a re-derived
value must come from a real run). Any C4 verdict decided against such an env is meaningless,
whether it renders `REPRODUCED` or `UNVERIFIED`. Poetry is a common research-Python lock format,
so the silent pass also suppresses R1 coverage (High/High) by routing a whole class of runnable
papers into a broken env.

## Goals & Success Metrics

- **No silent pass.** A build that declares dependencies but installs none is `EnvBuildFailed`,
  never a built env. *Measured by:* a mutation-checked test — if the empty-venv guard is removed
  or loosened, the suite fails.
- **Poetry is a first-class policy.** A poetry-only checkout is classified `"poetry"` (not
  `"best-effort"`) and built by a poetry-aware path. *Measured by:* precedence tests and a
  descriptor render test.
- **The replay contract is preserved.** Every existing policy string (`lockfile`, `declared`,
  `best-effort`) renders byte-identically; the new vocabulary is additive. *Measured by:*
  existing determinism/bundle tests stay green, plus a new cross-process determinism test.
- **The Perrin re-probe is honest.** The dev-time probe records whether the poetry policy removes
  the empty-env problem and whether the recorded drift stands — no result is forced (constraint
  #3).

## User Personas & Scenarios

- **The verifier (primary).** Runs `plumb verify <paper> <repo>` on a paper whose repo is a
  poetry project. Before this unit: the env silently builds empty and the verdicts are garbage.
  After: the env is built from the poetry project, or the run fails loudly with a named cause.
- **The corpus maintainer.** Re-probes Perrin and records the honest env outcome for the corpus
  (R1). Needs the probe to be reproducible and path-free.

## Requirements

### Must-have

1. **Detect `poetry.lock`.** `ManifestScan` (`src/plumb/intake/manifest.py:25-35`) gains a
   `poetry_lock: Path | None` field; `scan_manifests` records it root-only; absence is `None`.
2. **Precedence** in `_dependency_policy` (`env.py:214-223`):
   `uv.lock` → `"lockfile"`; else `poetry.lock` → `"poetry"`; else `requirements*.txt` →
   `"declared"`; else `"best-effort"`. (Decided: `uv.lock > poetry.lock > requirements`.)
3. **Policy vocabulary** (`env.py:81`): add `"poetry"` with a `policy_detail` naming
   `poetry.lock`. Existing strings are unchanged.
4. **A poetry-aware build.** The real runner builds a poetry project via the `uv` two-step shape
   proven in `tools/perrin_gate_run.py:84-112` (`uv venv --python <pin>` then
   `uv pip install <checkout_dir>`), not via `uv sync`. `_policy_command` no longer has a
   silent fall-through that a poetry project can reach.
5. **The empty-env guard, in the real runner.** *(Decided: guard lives in the real runner(s);
   `build_environment` is unchanged, so stub-runner tests are untouched.)* After a zero-exit
   build on a policy that **declares dependencies** (`lockfile`, `poetry`, `declared`), the
   runner inspects `checkout_dir/.venv` and reports `EnvBuild(ok=False, ...)` when the
   environment is **empty**, which the existing `env.py:158` gate turns into `EnvBuildFailed`.
   **Definition of "empty" (must be pinned):** no installed distribution — i.e. no
   `*.dist-info` / `*.egg-info` directory under any `site-packages` in the venv. Note this is
   *distribution*-level, not *third-party*-level: a dep-free project that still installs its own
   package (which `uv pip install <checkout>` does, producing a `dist-info`) is **not** empty and
   must not be failed. A `"best-effort"` build with no declared deps is **not** failed for being
   empty (a dependency-less project is legitimate) — pinned by a test so no existing best-effort
   run is retroactively demoted.
6. **Determinism.** The descriptor's `to_text()` render for the new policy is byte-identical
   across processes (the `PYTHONHASHSEED` child-process pattern, `tests/run/test_trace.py:172-183`).

### Should-have

7. **Dev-time poetry probe.** A `tools/poetry_env_probe.py` (mirroring `tools/notebook_probe.py`)
   that runs the engine poetry build by hand, never imported by tests, network at dev time only.
8. **Perrin re-probe.** Re-run Perrin through the poetry policy at its recorded boundary and
   record the outcome. Update the committed fixture (`fixtures/gate/perrin/`) and its pinned
   tests (`tests/gate/test_perrin_replay.py`, `tests/gate/test_panel_corpus.py`) **only if the env
   outcome actually changes**; otherwise add a probe note to the Perrin README.

### Nice-to-have

9. Detect poetry **without** a `poetry.lock` (a `pyproject.toml` with `[tool.poetry]` deps) and
   route it away from a silent `best-effort` empty build.

## Technical Considerations

- **Architecture fit.** This is a C2 (intake) change; it feeds C3 (run adopts `.venv`) and C4
  (verdicts). No verdict logic changes — execution is untouched; this only stops an unreal env
  from reaching it. No network in tests, no LLM, no egress.
- **Replay contract (load-bearing).** The `policy` string flows into `RunTrace.env_policy` →
  `trace.json` and `EnvDescriptor.to_text()` → `environment.txt` in the bundle. AgroDesign, rcai
  and Perrin all commit `"best-effort"` bytes, so the poetry value must be **additive** and the
  guard must not change any other policy's behaviour or wording.
- **Guard vs. stubs (resolved).** Every `TestBuildEnvironment` stub
  (`tests/intake/test_env.py:210-249`) and `--no-env-build` (`cli/live.py:251`) returns
  `ok=True` with no `.venv`. Placing the guard in the real runner(s) keeps `build_environment`'s
  common path and all stubs unchanged; the guard's predicate is a pure helper unit-tested against
  synthetic empty/non-empty `.venv` directories in `tmp_path`.
- **Runner wiring.** `uv_sync_runner` (`env.py:166-192`) becomes policy-aware (dispatch poetry to
  the two-step build) or a sibling `poetry_runner` is added with a thin dispatcher; `live.py`
  uses the dispatcher. Naming is a tech-plan detail; the constraint is one default runner
  reachable from `cli/live.py:252` that covers every policy. The engine poetry build uses the
  descriptor's python pin (`uv venv --python <pin>`); the paper-era boundary option
  (`--exclude-newer`) stays a dev-time probe concern (Perrin built at 3.10 / 2024-06-18,
  `tools/perrin_gate_run.py:57-58`), not an engine default.
- **Feasibility evidence.** `uv` cannot read `poetry.lock`, but `uv pip install <checkout>`
  resolves a poetry project through its build backend — proven by `perrin_env_runner`
  (`tools/perrin_gate_run.py:84-112`), which built Perrin this way. This unit lifts that shape
  into the engine runner.
- **Offline vs. dev-time split.** The classification, precedence, guard, and descriptor
  determinism are offline/CI-testable. The actual poetry build (network) and the Perrin re-probe
  live only in `tools/`, matching acceptance (4) of the brief.
- **No lint/typecheck configured** — `pyproject.toml` has pytest only; the gate is
  `uv run pytest -q` green.

## Risks & Open Questions

- **R1 (binding coverage, High/High).** Partially retired: unblocks poetry-locked repos. Not a
  full R1 fix (still needs the paper to expose machine-readable numbers).
- **Guard false positives.** A project that legitimately declares zero dependencies but is a
  poetry/requirements project would be failed. *Mitigation:* the guard is keyed on the policy
  declaring deps; a truly dep-free project is almost always `best-effort`. Watch during the
  Perrin probe; revisit if a real dep-free case appears.
- **Perrin's drift may not clear.** The paper-era boundary cannot build `qdldl` on arm64
  (`fixtures/gate/perrin/README.md:91-98`); the poetry policy may remove the *empty-env* problem
  while the recorded drift stands. The probe must record whichever is true — do not assume.
- **Vocab drift.** Adding `"poetry"` must not perturb `best-effort`. Covered by the determinism
  test and the existing fixture tests.
- **Open question (nice-to-have 9):** `[tool.poetry]` deps without `poetry.lock` remain a silent
  best-effort path. Deferred unless the Perrin probe or a panel paper exposes it.

## Out of Scope

- Container isolation for running untrusted code (a separate C3 follow-on).
- Making uv read `poetry.lock` (it cannot) — the build uses `uv pip install`.
- Any change to C4 verdict logic, tolerance, or the verdict vocabulary.
- Changing the meaning or wording of the existing `lockfile` / `declared` / `best-effort` policies.
- A general dependency-less-project heuristic beyond the policy gate.
- Hosting, LLM assistance, or any network path in tests/CI.

## Acceptance Criteria (written first — the repo is test-first)

Offline (CI, no network):

1. `ManifestScan` reports `poetry.lock` when present and `None` when absent, root-only.
2. `_dependency_policy` precedence holds: `uv.lock` beats `poetry.lock` beats `requirements*.txt`
   beats none; a poetry-only checkout yields `policy == "poetry"` with a detail naming
   `poetry.lock`.
3. `EnvDescriptor.to_text()` for the poetry policy is byte-identical across processes
   (`PYTHONHASHSEED` child), and the `lockfile`/`declared`/`best-effort` renderings are unchanged.
4. Empty-env guard: a real-runner path that exits 0 but leaves an empty `.venv` (no `*.dist-info`
   under `site-packages`) yields `EnvBuild(ok=False)` → `build_environment` raises
   `EnvBuildFailed`; a non-empty `.venv` yields `ok=True`; a `best-effort` empty build is **not**
   failed. Mutation-checked: removing/loosening the guard fails the suite.
5. `_policy_command` for `"poetry"` no longer falls through to a bare `uv sync`.

Dev-time (not in tests/CI):

6. `tools/poetry_env_probe.py` builds a poetry repo's env via the engine path and prints the
   policy + freeze; never imported by tests, run by hand.
7. The Perrin re-probe records the honest outcome (drift clears or stands) and either updates
   the fixture + pinned tests or adds a note.

Docs & hygiene:

8. `docs/technical/CAPABILITY_ROADMAP.md` (C2/C5), `docs/ROADMAP.md`,
   `fixtures/gate/perrin/README.md`, and `panel-run/screening.md` are updated to reflect the
   shipped state; no over-claiming.
9. `uv run pytest -q` stays green; no test touches the network.
