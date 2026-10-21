title:	task: Perrin re-probe at the recorded drift boundary
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
number:	26
--
C2's poetry policy landed (2026-10-17) but Perrin has not been re-probed at its recorded drift
boundary (2024-06-18), and no claim is made that the drift cleared
(docs/technical/CAPABILITY_ROADMAP.md:283-290).

Scope: re-run the Perrin case at the recorded boundary with the poetry env policy, record whether
the environment now builds and whether the earlier 14 refuted divergences change. Evidence goes in
`fixtures/gate/perrin/`, with the honest outcome (cleared or still drifted) written down.

Acceptance: the probe is recorded with commands, tool versions, and the run id; if it cannot run
on this machine, that is documented as a named blocker rather than silently skipped. Requires
network for the env build; no fixture may be hand-edited to make it pass.
