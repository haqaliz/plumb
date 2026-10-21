# PRD — Perrin re-probe after the poetry policy

Issue: #26.

## Requirements

- **R1** — a dev-time probe that resolves the pinned rev and builds the environment through the
  **generic** C2 path (`describe_environment` + `uv_sync_runner`), printing policy, pin, ok and
  package count.
- **R2** — the outcome is recorded in `fixtures/gate/perrin/`, including what it does *not*
  establish (the run was not re-executed; drift did not clear).
- **R3** — the committed trace/verdicts/labels are untouched; no fixture is edited.
- **R4** — the scheduled 4–12 h re-run is named, with its command, as the next step.
- **R5** — the C5 status no longer implies the poetry policy is an open blocker.

## Non-goals

- Running the 12 h scenario in this session.
- Changing any label or verdict.

## Acceptance

`reprobe_20261021.md` with the observed output; `CAPABILITY_ROADMAP.md` updated; full suite green
(the probe is not imported by tests).
