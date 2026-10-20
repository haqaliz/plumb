# PRD — run knobs: `--timeout-seconds` and `--run-dir`

Issue: #19. Phase 1's last should-have (`docs/ROADMAP.md`), deferred at launch because it is not
on the demo path.

## Problem

`plumb verify` hard-codes a 1800 s timeout and a deterministic run area under
`~/.plumb-runs` (`src/plumb/cli/live.py:76,182`). A user whose paper's code legitimately takes
longer cannot raise the limit; a user who wants the run's working copy and captured objects
somewhere specific (a mounted disk, a scratch volume, a CI artifact path) cannot move them. The
engine runner already supports both (`run_and_capture(run_dir=, timeout_seconds=)`), so the gap
is CLI surface only.

## Requirements

- **R1 — args.** `plumb verify` gains `--timeout-seconds SECONDS` and `--run-dir DIR`, both shown
  in `--help`.
- **R2 — validation.** A non-positive or non-numeric timeout is a usage error (exit 2, one
  argparse message, never a traceback). Both knobs combined with `--from-record` are a usage
  error: replay runs nothing.
- **R3 — timeout is honoured.** The value reaches `run_and_capture`; a process that outlives it is
  killed (process group) and recorded `TIMEOUT`, every claim `UNVERIFIED` with that cause, exit 1.
  Default unchanged: 1800 s.
- **R4 — run dir is honoured, safely.** The working copy and object store are created under the
  given directory instead of the derived slot, and the derived slot is not created. An explicit
  directory that already holds files is refused before running — never deleted, never overwritten.
- **R5 — nothing else moves.** The pinned checkout is still never touched; the trace still records
  no absolute run path; stdout/JSON stay byte-identical for identical inputs.

## Non-goals

- Resource caps beyond the timeout, container isolation (#21).
- Moving the checkout cache; a `PLUMB_RUNS`-style env var.
- Any change to the verdict contract or the cause vocabulary.

## Acceptance

`tests/cli/test_live_spine.py`: help lists both; bad values exit 2; a sleeping entrypoint is
killed at the given timeout with `TIMEOUT` and exit 1; a `--run-dir` run puts `work/` and
`objects/` there while the work root stays absent; a non-empty `--run-dir` is refused with its
file intact; `--from-record` rejects both. Full suite green, offline.
