title:	task: C3 resource caps and container isolation
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
number:	21
--
C3 has a wall-clock timeout; docs/technical/CAPABILITY_ROADMAP.md:178 names two gaps:
resource caps beyond the timeout, and container isolation.

Scope:
- Caps: total captured bytes per run, per-artifact size, and a cap on the number of captured
  artifacts, each a named `UNVERIFIED`-class cause (never a silent truncation).
- Isolation: a seam for running the entrypoint in a container, feature-detected; when absent the
  current subprocess runner is used unchanged and the run is marked as non-isolated in the trace.

Acceptance: caps are tested with stub programs (no network, no real container); an exceeded cap is
a named cause and never a `DIVERGED`; the default path is byte-identical to today's traces.
