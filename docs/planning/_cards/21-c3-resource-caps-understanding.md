# Understanding — C3 caps (#21)

## What the work really is

The runner already has a wall clock. The missing safety is against *evidence volume*: a program
can write a 2 GB `results.json` or flood stdout, and `capture_outputs` would read it into memory
and copy it into the object store. Two caps — per artifact and total — refuse that evidence before
it is read, with a recorded cause, so nothing downstream can bind to a partial file.

Container isolation is the other half of the issue and is **deferred with a stated reason**: it
needs Docker in CI plus a new dependency, and C2 already records subprocess isolation as the
posture (`src/plumb/intake/env.py:50-57`). Nothing here pretends otherwise.

## Contradictions and decisions

- The `run` docstring said "resource caps ... recorded, not enforced". This change makes that
  sentence false; it is rewritten, not left stale.
- A cap must never look like `NO_ARTIFACT` (a silent empty run) nor like `NO_BINDING`. The cap
  causes are **run-level**, checked before per-claim binding, so a capped run is `UNVERIFIED`
  with its cap cause for every claim.
- Defaults (64 MiB per artifact, 256 MiB total) are generous enough for real outputs and bounded
  enough to stop an accidental log dump.
- `shortcut:` the runner still buffers stdout/stderr in memory before the cap applies; the cap
  bounds what is stored and read, not peak process memory. Upgrade to streaming reads if a real
  process floods memory.

## Pipeline placement

C3. Causes feed C4's closed vocabulary; no verdict is invented.
