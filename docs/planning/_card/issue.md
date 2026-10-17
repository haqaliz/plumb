# feat poetry-env-policy — C2 poetry env policy

Source: `plumb-next` handoff brief, 2026-10-17 (no GitHub issue; slug id).

## Brief

Make C2 never record an empty environment as built for poetry-only projects, and add a
real poetry env policy. Today `_dependency_policy` (`src/plumb/intake/env.py:214-223`)
recognizes only `uv.lock`, so a repo with a `poetry.lock` and no `uv.lock`/`requirements*.txt`
falls to `"best-effort"`, whose `uv sync` yields an empty venv recorded as a built env — a
silent success that must not pass (guardrail #3). Acceptance tests, written first: (1) a
checkout with `poetry.lock`+`pyproject.toml` and no `uv.lock`/`requirements*.txt` gets a
distinct poetry policy in the env descriptor, not `best-effort`; (2) a `uv sync` "success"
that leaves an empty venv is `EnvBuildFailed`, never a built env (mutation-checked, like the
freshness/false-`DIVERGED` guards); (3) the descriptor renders deterministically and
byte-identical across processes, offline with a stub runner; (4) no test touches the network
— the one real poetry build runs only via a `tools/` dev-time script, re-probing Perrin
(`fixtures/gate/perrin/`) and recording whether the policy removes its recorded drift or the
selection outcome stands; (5) `uv run pytest -q` stays green. Keep the offline/refusal slice
and the dev-time build slice separate so the first lands test-first without network.

## Grounding (from plumb-next ranking)

- Named as an unbuilt engine gap in three planning files:
  - `docs/planning/cross-paper-coverage/panel-run/screening.md:295-298`
  - `docs/planning/cross-paper-coverage/r1-report/spec.md:26-31`
  - `docs/technical/CAPABILITY_ROADMAP.md` C5 status (line ~260-264)
- Capability: **C2 — Artifact intake & pinned environment** (follow-on slice).
- Risk: **R1** (binding coverage, High/High) + guardrail #3 (never a silent pass).
