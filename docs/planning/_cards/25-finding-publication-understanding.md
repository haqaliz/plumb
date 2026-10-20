# Understanding — first finding (#25)

## What the work really is

Not code: the *artifact* that publication needs, plus a test that keeps it honest. The corpus has
exactly one confirmed `DIVERGED` (AgroDesign §4.1, `0.034` reported, `0.03455` printed). ETHICS.md
requires a human review, a right of reply, and a replayable bundle before anything goes out.

## The design that avoids a new system

A Markdown note under `docs/findings/` with the claim id, both values, the replay commands, the
review record, and an **open checklist** (nothing is checked). A test in `tests/bundle/` verifies
the bundle, extracts its single `DIVERGED`, and asserts the note carries exactly those numbers —
so the note cannot drift into a claim the evidence does not support.

## Decisions

- **The note says "not published, not sent"** in its status line and a test asserts no checklist
  item is checked: publishing is an owner act, not a commit.
- **The draft reply is included but marked "not sent"** — the process is ready, the act is not
  taken.
- **No new CLI and no findings database**: one human-reviewed document per finding.

## Pipeline placement

Documentation over C6's bundle; no engine change.
