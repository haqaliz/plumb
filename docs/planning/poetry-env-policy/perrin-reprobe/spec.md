# Spec — perrin-reprobe (poetry-env-policy, aspect 2)

Source: `docs/planning/poetry-env-policy/prd.md` (approved 2026-10-17). This is the **dev-time**
aspect: run the real poetry build by hand, re-probe Perrin, and record the honest outcome. It
depends on aspect 1 (`poetry-policy`) and never runs in tests/CI.

## Problem slice

Perrin (`fixtures/gate/perrin/`) is the only committed poetry case. Its env was built by a bespoke
dev-time runner (`tools/perrin_gate_run.py:84-112`) at a drifted boundary (`--exclude-newer
2024-06-18`, Python 3.10) and recorded as `"best-effort"`. Aspect 1 classifies poetry correctly;
this aspect exercises the *real* poetry path by hand and records whether the empty-env problem is
gone and whether the qdldl/arm64 drift stands — **without forcing a result.**

## In scope

- A dev-time probe `tools/poetry_env_probe.py` that builds a poetry repo via the engine runner
  and prints the policy + freeze; never imported by tests.
- Re-probe Perrin through the poetry policy at its recorded boundary; record the outcome.
- Update the committed Perrin fixture and pinned tests **only if the env outcome actually
  changes**; otherwise add a probe note.
- Sync the status docs.

## Out of scope

- Any change to the offline engine slice (aspect 1).
- Re-selecting or relaxing the panel rule.
- Forcing the drift to disappear; the qdldl/arm64 wall may stand — record it.

## Acceptance criteria

1. `tools/poetry_env_probe.py` exists, is run by hand (`uv run tools/poetry_env_probe.py`), has
   the "never imported by tests" docstring convention, and builds a poetry repo through the
   engine runner.
2. The Perrin re-probe produces a recorded outcome: `fixtures/gate/perrin/README.md` gains a
   dated probe note stating whether (a) the poetry policy removes the empty-env problem and
   (b) the recorded drift (qdldl/arm64, earliest buildable boundary) stands.
3. If the outcome changes the record: `fixtures/gate/perrin/environment.txt`, `trace.json`
   (`env_policy`), and any affected `objects/`, `verdicts.json`, `drift.json` are regenerated,
   and `tests/gate/test_perrin_replay.py` / `tests/gate/test_panel_corpus.py` are updated to the
   new pinned values — all committed files remain path-free
   (`test_no_committed_file_carries_a_local_path` stays green).
4. If the outcome does not change the record: no fixture bytes move; the note records why.
5. Status docs updated honestly: `docs/technical/CAPABILITY_ROADMAP.md` (C2/C5),
   `docs/ROADMAP.md`, and `docs/planning/cross-paper-coverage/panel-run/screening.md` name the
   shipped policy and the remaining named gap (if any). No over-claiming.
6. `uv run pytest -q` stays green; no test touches the network.

## Dependencies & sequencing

After aspect 1 merges. Requires network at dev time (uv build) — evidence recorded, not in CI.
The committed Perrin fixture churn is the main risk; the plan keeps "record-only" as the default
when the outcome is unchanged.

## Open questions / risks

- Perrin's boundary problem is qdldl/arm64, not poetry-emptiness; expect the drift to stand and
  the policy **label** to change. If regenerating the fixture is pure label churn with no new
  information, prefer the README note over moving committed bytes (decide at probe time, record
  the reasoning).
