# Understanding — Perrin re-probe (#26)

## What the work really is

Two halves, and only one is affordable here:

| Half | Cost | This card |
|---|---|---|
| Does the **generic poetry policy** build the pinned checkout? | minutes | **done** — builds, 134 packages |
| Does the **run** at the 2024-06-18 boundary change the 14 refuted divergences? | 4–12 h | **not run** — recorded as a named blocker |

The honesty rule is the same one the corpus already follows: the environment building is not the
drift clearing, and a fixture is never edited to make a narrative pass.

## Affected areas

`tools/perrin_env_probe.py` (new dev-time, networked, never imported by tests),
`fixtures/gate/perrin/reprobe_20261021.md` (the record), `CAPABILITY_ROADMAP.md` C5 status.

## Decisions

- **Probe the env, not the science.** The env was the policy's own gap; the 12 h run is a
  scheduling decision, and running a truncated version would produce a number that means nothing.
- **Current resolve, no boundary.** The generic policy has no boundary knob; boundary selection
  stays in `tools/perrin_gate_run.py`, whose recorded 2024-06-18 boundary still stands.
- **The committed record is untouched.** A re-run writes new evidence beside it, never over it.

## Pipeline placement

C2/C5. No engine change; no verdict change.
