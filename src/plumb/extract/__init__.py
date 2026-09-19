"""Claim extraction: the records a paper's quantitative claims are read into.

This package extracts *candidate* claims only. It emits no verdicts — no
`REPRODUCED`, `DIVERGED`, or `UNVERIFIED` — because only re-execution may assign one
(`CLAUDE.md` #1).
"""
