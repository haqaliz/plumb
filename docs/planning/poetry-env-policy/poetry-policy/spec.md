# Spec — poetry-policy (poetry-env-policy, aspect 1)

Source: `docs/planning/poetry-env-policy/prd.md` (approved 2026-10-17). This is the **offline,
CI-testable** aspect: classify poetry and never record an empty environment as built. The
dev-time build/probe is aspect 2 (`perrin-reprobe`).

## Problem slice

A poetry-only checkout (`poetry.lock`, no `uv.lock`/`requirements*.txt`) is currently classified
`"best-effort"` and built with a bare `uv sync`, which modern uv cannot honour → it exits 0 and
leaves an **empty `.venv`**, recorded as `EnvBuild(ok=True)`. This aspect makes the policy honest
and stops the silent pass, entirely offline (stub runner / monkeypatched subprocess; no network).

## In scope

- `ManifestScan.poetry_lock` detection (root-only).
- Policy precedence `uv.lock > poetry.lock > requirements*.txt > best-effort`; new `"poetry"`
  policy value and detail.
- A poetry-aware ordered command set (`uv venv` + `uv pip install <checkout>`), replacing the
  silent `uv sync` fall-through for poetry.
- The empty-env guard in the real runner, applied to dependency-declaring policies
  (`lockfile`/`poetry`/`declared`); `best-effort` is exempt.
- Descriptor determinism for the new policy.

## Out of scope

- The real poetry build and the Perrin re-probe (aspect 2, dev-time).
- Detecting `[tool.poetry]` without a `poetry.lock` (PRD nice-to-have 9).
- Any change to verdict logic, C3, C4, or the existing policy strings' wording.

## Acceptance criteria (testable; written first)

1. `scan_manifests` records `poetry_lock` when present and `None` when absent; root-only.
2. `_dependency_policy`: poetry-only → `"poetry"` with a detail naming `poetry.lock`;
   `uv.lock`+`poetry.lock` → `"lockfile"`; `poetry.lock`+`requirements.txt` → `"poetry"`.
3. `EnvDescriptor.policy` vocabulary documents `"poetry"`; `to_text()` for the poetry policy is
   byte-identical across processes (PYTHONHASHSEED child), and the `lockfile`/`declared`/
   `best-effort` renders are unchanged.
4. `_policy_commands` for `"poetry"` returns the ordered `uv venv` + `uv pip install <checkout>`
   commands; no policy reaches a bare `uv sync` fall-through except `lockfile`/`best-effort`.
5. Empty-env guard: with `subprocess.run` monkeypatched to exit 0 and a pre-made **empty**
   `checkout/.venv`, `uv_sync_runner` returns `ok=False` under a dependency policy, and
   `build_environment` raises `EnvBuildFailed`; a **non-empty** `.venv` returns `ok=True`; a
   `best-effort` empty build returns `ok=True` (exempt).
6. Mutation-checked: disabling the guard (`_venv_is_empty` → `False`) makes criterion 5's
   assertion fail (the `TestMutations` convention of
   `tests/verify/test_false_diverged_guard.py:280-307`).

## Dependencies & sequencing

Independent of aspect 2; ships first (it is the correctness fix and unblocks the corpus).
`tests/run/`, `tests/verify/`, and the CLI are untouched (the runner name and seam are stable).

## Open questions / risks

- `uv venv --python <pin>` only accepts a concrete version; the descriptor pin may be a
  specifier (`>=3.9` from `requires-python`). Handled by passing `--python` only for a concrete
  pin (see plan). Watch at the aspect-2 probe.
- The guard keys on `checkout_dir/.venv` (matching `run/runner.py:174`); a runner that installs
  elsewhere would false-positive. All three shipped policies target `.venv`, so this is safe.
