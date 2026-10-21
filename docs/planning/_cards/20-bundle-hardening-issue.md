title:	feat: close the C6 bundle hardening gaps
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
number:	20
--
C6 is built; these five gaps are named in docs/technical/CAPABILITY_ROADMAP.md:320-321.

1. `plumb bundle` CLI (verify / inspect a bundle dir without reaching into Python).
2. Tar packaging of a bundle dir (single artifact, deterministic bytes).
3. Timestamps (a signed time assertion in the manifest, no third-party dependency required).
4. Key rotation (an allowed_signers file with more than one key, and a documented rotation path).
5. Transparency log / sigstore (optional, feature-detected, never a hard dependency).

Acceptance per item: behaviour test-first, offline, no new required runtime dependency, existing
bundles still verify, `verify_bundle` still reports named causes and never raises on content.
