title:	chore: add --timeout-seconds and --run-dir knobs
state:	OPEN
author:	haqaliz (Ali Haqiqi)
labels:	enhancement
comments:	0
assignees:	
projects:	
milestone:	
issue-type:	
parent:	
sub-issues:	
sub-issues-completed:	
blocked-by:	
blocking:	
number:	19
--
Phase 1 leftover (docs/ROADMAP.md:43-45, docs/LAUNCH.md Deferred).

Add two should-have CLI knobs to `plumb verify`:
- `--timeout-seconds N` → threaded into the C3 runner's timeout (kills the whole process group).
- `--run-dir DIR` → run area override (working copy + object store live there instead of the default).

Acceptance:
- Both parse and appear in `--help`; bad values exit 2 with a usage message, never a traceback.
- Defaults unchanged (existing tests stay green).
- Timeout is honoured end-to-end (a stub entrypoint that sleeps is killed, `TIMEOUT` recorded).
- `--run-dir` is respected for the working copy and the object store; the pinned checkout is still never touched.
- Offline, deterministic, `uv run pytest -q` green.
