# Brief: value-kinds-compare

Source: inline brief (plumb-next handoff, 2026-10-01). No GitHub issue — id is a slug.
Owner: aliz. Branch: feat/value-kinds-compare/aliz.

## Brief

Extend C4's compare so PlusMinus, Interval, Range and Approximate claims (already
extracted and serialized by C1; src/plumb/extract/value.py) are decided instead of
refused as UNSUPPORTED_VALUE_KIND (src/plumb/verify/compare.py:11-12). Pin the
semantics in new D-decisions in the D1-D8 style: a PlusMinus is compared by its
centre within the paper's written precision plus its stated margin, Interval/Range
by closed-band membership, Approximate by a pinned policy (written-precision band
or explicit-tolerance-required); every decision conservative, never a false
REPRODUCED. Tests first: each new kind decides on synthetic runs, band-edge and
harness-failure cases stay UNVERIFIED and never DIVERGED (extend the
mutation-checked guard), verdicts serialize byte-identically, and the catalogue
test still proves every cause in the closed vocabulary is emitted. Caveat: the
band-vs-precision semantics are R2-sensitive and un-pinned today — pin them before
implementing, and record the decision in docs/planning/binding-verdict/prd.md.

## Background from plumb-next (why this slice)

- C4 is the moat and the critical path (docs/technical/CAPABILITY_ROADMAP.md:147;
  docs/ROADMAP.md R1/R2 are High/High). The first slice deferred ±/CI/range/~ to
  UNSUPPORTED_VALUE_KIND (docs/planning/binding-verdict/prd.md:236); the record
  layer already extracts and serializes all four kinds (src/plumb/extract/value.py:
  101-146, serialize.py:180-183), so only comparison is missing.
- It is the R1 mitigation a real paper will hit: the Phase 0 gate is met on one
  paper (docs/ROADMAP.md:29-33) and Phase 1's remaining work is "harden against
  real repos (R1 — cross-paper coverage is still unmeasured)" (docs/ROADMAP.md:
  41-45). Real papers write ±/CI/range; today every such claim is refused before
  comparison.
- It sets up C5's corpus (docs/technical/ARCHITECTURE.md:146-152) to hold
  uncertainty-valued claims.