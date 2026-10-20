# Understanding — run knobs (#19)

## What the work really is

Two pass-throughs from the shell to the C3 runner, plus the safety rule that makes an explicit
run area safe. The engine already accepts both values: `run_and_capture(..., run_dir=,
timeout_seconds=)` and `run_entrypoint` already implement the timeout kill and the
"refuse a non-empty explicit run dir" guard. The CLI hard-codes both
(`src/plumb/cli/live.py:76,182-186`), so the work is argument plumbing and its tests — not a new
runner.

## Affected areas

| Area | File | Change |
|---|---|---|
| Shell | `src/plumb/cli/__init__.py` | two `verify` arguments; reject them with `--from-record` |
| Live spine | `src/plumb/cli/live.py` | explicit run dir (no `_reset`!), explicit timeout |
| Tests | `tests/cli/test_live_spine.py` | one class, TDD first |
| Docs | `docs/ROADMAP.md`, `docs/LAUNCH.md` | drop the deferred line once green |

## Decisions and ambiguities

- **`--run-dir` relocates the run area only** (working copy + object store), not the checkout
  cache. The checkout cache is keyed by repo URL, not by run; moving it would change `--rev`
  behaviour for no user value.
- **An explicit run dir is never wiped.** The deterministic slot (`~/.plumb-runs/run-…`) is
  cleared on re-run by design; a user-supplied directory must not be `rmtree`d. The existing
  `_fresh_run_dir` already refuses a non-empty dir — that guard is the safety, and it maps to
  `SPINE_ERROR` (exit 1), no new cause vocabulary.
- **Timeout is live-only.** Both knobs are meaningless with `--from-record`, so passing either
  is a usage error (exit 2), consistent with the existing `--rev`/`--bindings` rejections.
- **Caps are not this card.** C3's "resource caps beyond the timeout" is issue #21; this card
  adds only the knob the runner already honours.

## Pipeline placement

C3 (execution), CLI surface. No verdict path changes, so no `DIVERGED` risk.
