# Spec: value-kinds-compare / compare

One aspect: the compare extension. `docs/planning/value-kinds-compare/prd.md` is
the requirements source; decisions D9–D13 supersede D3
(`docs/planning/binding-verdict/prd.md:80-84`).

## Problem slice

`decide()` (`src/plumb/verify/compare.py:98-125`) refuses `PlusMinus`, `Interval`,
`Range`, `Approximate` at the D3 kind gate (compare.py:115-116). Extend it to decide
all six kinds with conservative, pinned semantics; remove the now-unemittable
`UNSUPPORTED_VALUE_KIND` cause from the closed vocabulary.

## In-scope

- Parse-side well-formedness guards in `src/plumb/extract/value.py`: `_plus_minus`
  refuses a negative margin (`0.87 ± -0.02` → `None`); `_interval`/`_range` refuse
  `low > high` (`CI [0.93, 0.81]` → `None`); `margin = 0` still parses (D9
  degeneracy). Rationale: C1 never invents a value; a malformed reported claim is
  refused as a non-claim with a named cause upstream, never compared.
- `PlusMinus` compare per D9, `Interval`/`Range` per D10, `Approximate` per D11,
  coarse-artifact check per D13, in the D1–D8 decision order.
- `UNSUPPORTED_VALUE_KIND` removal per D12, coordinated (causes, tables, catalogue,
  closed-set tests, docs).
- Fixture immutability: no fixture claim moves on either path (the repo's floor).

## Out-of-scope

- The binding proposer, notebook-cell locators, C3 notebook capture.
- `%` vs percentage-points unit rule.
- Per-kind default tolerances (D2).
- Choosing/running the next real paper.

## Acceptance criteria (failing tests first)

1. `parse_value("0.87 ± -0.02") is None` and `parse_value("CI [0.93, 0.81]") is
   None`; `parse_value("0.87 ± 0")` still yields `PlusMinus`; no fixture claim
   moves on either path (extract + pdf seam suites).
2. A `PlusMinus` bound to a fresh value inside `[center − margin − hc − hm, center
   + margin + hc + hm]` is `REPRODUCED` with the band in evidence; inside the
   tolerance only → `WITHIN-TOLERANCE`; outside both → `DIVERGED` with
   `review_required`; trailing-zero-integer centre with no tolerance →
   `PRECISION_AMBIGUOUS` (D1a parity); percent claims with `scale` decide on the
   scaled band with the D7 half-unit trap pinned; hostile ambient `Decimal`
   context stays pinned.
3. `Interval`/`Range` decide by closed membership in `[low − hl, high + hh]`;
   tolerance widens; D1a does not apply to endpoints; same policy for both kinds.
4. `Approximate` decides exactly like a `Point` (D11): D1 band, D2 tolerance, D7
   point rule in full.
5. D13: a band-kind value outside its band, artifact coarser than the nearest
   boundary whose own half-unit reaches it → `ARTIFACT_PRECISION_COARSER`; a
   mutation that loosens the rule fails a dedicated test; inside the band, band
   kinds need no coarseness check.
6. `UNSUPPORTED_VALUE_KIND` is gone from `CAUSES`; the catalogue union and the
   verdict-record closed-set tests pass with the exact smaller set; every test
   that referenced the cause is re-homed; `grep -rn UNSUPPORTED_VALUE_KIND src/
   tests/` returns nothing.
7. The full suite stays green and offline; `plumb verify --from-record` on the
   AgroDesign record still replays byte-identical.

## Dependencies & sequencing

- Task A (parse guards) and Task B (`PlusMinus`/`Interval`/`Range`) are disjoint
  in files and parallelizable. Task C (`Approximate` + D13) follows B (same
  files). Task D (vocabulary removal) follows B+C: the catalogue test breaks at
  the end of C, which is D's RED. Final integration runs the whole suite +
  fixture gate + record replay.

## Open questions

- None — all pinned in the PRD (D9–D13) or here. The D13 nearest-boundary choice
  is the subtlest rule; its mutation test is mandatory.