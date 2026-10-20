title:	feat: C7 statcheck/GRIM internal-consistency path
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
number:	23
--
Whole capability, unbuilt (docs/technical/CAPABILITY_ROADMAP.md:323-335). Unblocked by the
pipe-table cell naming slice.

Scope: for PDF-only papers with no runnable artifact, run statcheck/GRIM-style checks against C1's
`StudyParameter` N records. Output is labeled an internal inconsistency, never a ground-truth
`DIVERGED`. New CLI surface (e.g. `plumb consistency <paper>`), deterministic and offline.

Acceptance: GRIM catches a known-inconsistent fixture and passes a consistent one; statcheck
recomputes p from test statistic + df and flags mismatches; every finding carries the labeled
weaker signal; no execution claim, no bundle verdict fields reused dishonestly.
