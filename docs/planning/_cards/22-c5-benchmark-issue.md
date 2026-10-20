title:	task: publish the C5 precision/recall benchmark
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
number:	22
--
The benchmark math exists (`src/plumb/corpus/metrics.py`) and `plumb corpus report` prints it, but
the public benchmark promised by Phase 2 is not published.

Scope:
- A reproducible benchmark run over the banked public corpus (the 3 real cases) producing a
  committed report, with label authority and refuted-verdict accounting explicit.
- Document how to add a case and how the number moves; link from README/METHOD.
- Grow the corpus only with cases that already run; do not fabricate coverage.

Acceptance: one command regenerates the committed benchmark report byte-identically; the report
states precision/recall with its denominator and label authority; docs/METHOD.md matches it.
