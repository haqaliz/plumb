# Understanding — poetry-env-policy (C2 follow-on)

Source: `docs/planning/_card/issue.md` (the `plumb-next` brief, 2026-10-17). Three dig
agents mapped the C2 env-build seam, the intake test/tooling surface, and the Perrin
drift record on 2026-10-17.

## What the work is really asking

Two distinct things, deliberately bundled:

1. **A correctness fix (the non-negotiable).** C2 can currently record an environment as
   *built* when nothing was actually installed. `_dependency_policy` recognises only
   `uv.lock` and `requirements*.txt` (`src/plumb/intake/env.py:214-223`); a poetry-only repo
   (a `poetry.lock`, no `uv.lock`/`requirements*.txt`) falls to `"best-effort"`, whose command
   is a bare `uv sync` (`env.py:256-263`). Modern uv no longer reads `[tool.poetry]` /
   `poetry.lock`, so that `uv sync` exits 0 and leaves an **empty `.venv`** — reported as
   `EnvBuild(ok=True)` and never inspected (`env.py:158` trusts `build.ok`; `run/runner.py:174`
   adopts any `checkout_dir/.venv` that `is_dir()`). That is a *silent pass* — exactly what
   `CLAUDE.md` constraint #3 forbids ("never a silent pass"). The verdict of any claim decided
   against such an env is untrustworthy.

2. **A build capability (the honest slice).** Add a real `poetry` env policy so a poetry-locked
   repo can actually be built, instead of the resolved-but-drifted workaround Perrin uses today.

## The gap, grounded in code

- **Manifests:** `ManifestScan` (`src/plumb/intake/manifest.py:25-35`) has **no `poetry_lock`
  field**; `scan_manifests` (`manifest.py:38-56`) never looks for `poetry.lock`. Repo-wide grep
  for `poetry` in `src/` is **empty**.
- **Policy selection:** one `if`-chain, `_dependency_policy` (`env.py:214-223`); vocabulary is
  declared `# "lockfile" | "declared" | "best-effort"` at `env.py:81`.
- **Policy → command:** one `if`-chain, `_policy_command` (`env.py:256-263`); the fall-through
  (`best-effort`, or any unknown policy) is `["uv", "sync", ...]` — the empty-venv path.
- **Build seam:** `build_environment` (`env.py:135-163`) runs the injected runner; the only
  failure gate is `if build is None or not build.ok:` (`env.py:158`). `EnvBuild`
  (`env.py:103-109`) carries only `ok`/`policy`/`detail` — **no venv path, no emptiness signal.**
- **Nothing detects a built-but-empty env** anywhere in `src/` (verified). The phenomenon is
  only documented in prose: `tools/perrin_gate_run.py:13-18`, `fixtures/gate/perrin/README.md:88-90`,
  `docs/technical/CAPABILITY_ROADMAP.md:260-261`, `panel-run/screening.md:266-267,296-297`.

## The Perrin precedent (the only committed poetry case)

- Perrin (`fixtures/gate/perrin/`) is a poetry repo pinned at `76ce145f`. Its committed env is
  **recorded drift**: the run built at `--exclude-newer 2024-06-18` (earliest buildable) via a
  bespoke dev-time runner `perrin_env_runner` (`tools/perrin_gate_run.py:84-112`) that does
  `uv venv` + `uv pip install <checkout>` — it **bypasses C2's `_policy_command` entirely**.
- Committed artifacts encode the *current* engine state: `fixtures/gate/perrin/trace.json`
  `"env_policy":"best-effort"`, `fixtures/gate/perrin/environment.txt:1` (header says
  `policy 'best-effort'`), `fixtures/gate/perrin/drift.json` (`"inconclusive": true`).
- Tests that must stay honest: `tests/gate/test_perrin_replay.py` pins `_TALLY = {REPRODUCED: 2,
  DIVERGED: 14}`, the drift assertions incl. the exact string `"inconclusive by construction"`,
  and `test_no_committed_file_carries_a_local_path`; `tests/gate/test_panel_corpus.py` pins the
  pooled totals (`TOTAL_CLAIMS = 102`, `BY_VERDICT`, `precision flagged 15`).

## Affected areas (mapped)

- `src/plumb/intake/manifest.py` — add `poetry_lock` to `ManifestScan` + scan it (+ docstring).
- `src/plumb/intake/env.py` — poetry branch in `_dependency_policy`; `policy` vocabulary
  comment (`env.py:81`); poetry branch in `_policy_command`; the empty-venv guard; possibly a
  `poetry_runner` alongside `uv_sync_runner`.
- `src/plumb/intake/__init__.py` — export any new symbol; `EnvBuildFailed` table row (`:22`).
- `src/plumb/cli/live.py:248-252` — only if the default runner must dispatch by policy.
- `tests/intake/test_env.py` — new poetry-policy cases (`TestDependencyPolicy`, `:117-144`); an
  empty-venv → `EnvBuildFailed` case in `TestBuildEnvironment` (`:210-249`); a determinism test
  in the `PYTHONHASHSEED` child-process style of `tests/run/test_trace.py:172-183`.
- `tests/intake/test_seam.py:21-42` — name lists if a new export is added.
- Dev-time only, never in tests: a `tools/poetry_env_probe.py` (mirroring
  `tools/notebook_probe.py`) and/or a re-run of `tools/perrin_gate_run.py` wired to the new runner.
- Docs to sync: `docs/technical/CAPABILITY_ROADMAP.md:260-261`, `docs/ROADMAP.md:67`,
  `README.md:138`, `fixtures/gate/perrin/README.md:88-98,124-125`,
  `docs/planning/cross-paper-coverage/panel-run/screening.md:266-267,296-297`.

## Place in the pipeline / guardrail check

**C2 — Artifact intake & pinned environment** (follow-on slice). Guardrail #3 (never a silent
pass) and constraint #5 (the re-derived value must come from a real run) are directly at stake:
an empty env makes C3/C4 verdicts meaningless. Risk register **R1** (binding coverage, High/High)
is the coverage side; this unit is also a *correctness* fix, not only a coverage win. No egress;
no LLM; execution stays the decider.

## Contradictions / tensions to flag (do not paper over)

1. **`best-effort` is part of the replay contract.** The descriptor's `policy` string flows into
   `RunTrace.env_policy` → `trace.json` and `EnvDescriptor.to_text()` → `environment.txt` in the
   bundle. AgroDesign, rcai **and Perrin** all commit `"best-effort"` bytes. So the poetry policy
   must be a **new vocabulary value** (`"poetry"`), and the empty-venv guard must **not**
   retroactively demote a legitimate `best-effort` run — only a genuinely empty env.
2. **The guard-vs-stub tension.** Acceptance test (2) wants an empty `uv sync` to become
   `EnvBuildFailed` *at the build seam*. But every existing `TestBuildEnvironment` stub
   (`tests/intake/test_env.py:210-249`) returns `EnvBuild(ok=True)` and creates **no `.venv`** —
   and `--no-env-build` stubs (`cli/live.py:251`) do the same. If `build_environment` blindly
   inspects `checkout_dir/.venv`, the entire suite breaks. The guard must distinguish "stub: no
   venv produced" from "real build: venv produced but empty". Candidate designs: (a) the check
   lives in the *real* runners (`uv_sync_runner`/poetry runner) which report `ok=False` on an
   empty venv, leaving `build_environment`'s common path and all stubs untouched; (b) a new
   `EnvBuild` field (e.g. an installed-package count, `None` = unknown/pass) set by real runners
   and enforced at the `env.py:158` choke point. **Must be resolved in the PRD** — it determines
   how "mutation-checked" (2) actually is.
3. **"Real poetry build" is dev-time only.** uv cannot read `poetry.lock`; the working build is
   `uv pip install <checkout>` (the `perrin_env_runner` shape), which needs the network. So the
   offline, CI-testable slice is (i) classify poetry + (ii) refuse an empty env; the *actual*
   poetry build and the Perrin re-probe are dev-time (`tools/`), exactly as acceptance (4) says.
4. **Does the poetry policy change Perrin's outcome?** It may *not*: Perrin's drift is the
   **qdldl/arm64** wall at the paper-era boundary, not merely poetry-emptiness. The re-probe
   must record the honest result — the policy may remove the empty-env problem while the
   qdldl wall (and thus the recorded drift) stands. Do not assume the drift disappears.

## Open questions (for the requirements interview)

1. **Policy precedence** — if `uv.lock` *and* `poetry.lock` both exist, which wins? (Likely
   `uv.lock` wins; `poetry` only when there is no `uv.lock`. Confirm vs `requirements*.txt`.)
2. **Guard placement & definition of "empty"** — tension #2 above; and the exact predicate
   (e.g. no `*.dist-info` under `site-packages`, or the `.venv` lacks any non-base package).
3. **Poetry command** — `uv pip install <checkout>`? `poetry install`? `poetry export | uv pip
   install -r -`? And the python-pin interaction (Perrin built 3.10 while the descriptor pins 3.11).
4. **Scope of this unit** — ship the offline refusal + policy classification now and leave the
   real poetry build + Perrin re-probe as a dev-time step of the same unit, or defer the build?
   The brief implies both, but they are separable.
5. **Perrin fixture churn** — regenerate the committed Perrin record under the new policy (which
   moves `environment.txt`/`trace.json` and possibly `objects/`/`verdicts.json` and the pinned
   tests), or leave Perrin as-is and record the re-probe as a selection note only?
6. **New export** — does a `poetry_runner` get exported from `intake` (touch `test_seam.py`), or
   does `uv_sync_runner` dispatch internally on `descriptor.policy` (no new export)?
