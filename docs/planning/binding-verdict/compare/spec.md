# Aspect `compare` — precision band, tolerance, and the verdict decision

Parent: [`../prd.md`](../prd.md) (M3; D1, D1a, D2, D3, D4, D7).

## Problem slice & outcome

A pure function: `(reported ClaimValue, units, located Decimal + its written half-unit,
tolerance?, scale?)` → `Decision(verdict, cause?, band?, tolerance_used?, delta?)`. No I/O, no
`Capture`, no run knowledge. All arithmetic in `Decimal` under a pinned local context.

## In scope

- **Kind gate (D3):** `Point`, `Bound` proceed; `PlusMinus`, `Interval`, `Range`,
  `Approximate` → `UNSUPPORTED_VALUE_KIND`.
- **Scale gate (D4):** percent claim (`units == "%"` or `%` in reported text) with no `scale`
  → `UNIT_UNDECLARED`. With `scale`, re-derived = located × scale; the artifact half-unit =
  written half-unit × scale (never the product's exponent — `0.87 × 100 = 87.00`).
- **Point:**
  - D1a: integer value ending in zero, no tolerance → `PRECISION_AMBIGUOUS`.
  - band = closed `[v − h, v + h]`, `h` = half-unit of the reported `Decimal`.
  - `re == v` → `REPRODUCED`, band recorded; `re` in band → `REPRODUCED`, band recorded.
  - D7: if artifact half-unit `a > h` (artifact coarser), and `v ∈ [re − a, re + a]` →
    `UNVERIFIED: ARTIFACT_PRECISION_COARSER`; if `v` is outside it, fall through.
  - tolerance: `abs t` → `[v − t, v + t]`; `rel r` → `[v − r|v|, v + r|v|]`; `rel` with
    `v == 0` → `NO_TOLERANCE`. Inside → `WITHIN-TOLERANCE`, tolerance recorded.
  - otherwise → `DIVERGED`, `review_required`.
- **Bound** (`op ∈ <, <=, >, >=`, threshold `m`): op satisfied → `REPRODUCED`; else with
  tolerance, threshold widened by `t` (or `r|m|`, `m == 0` with `rel` → `NO_TOLERANCE`) in the
  permissive direction, satisfied → `WITHIN-TOLERANCE`; else `DIVERGED`. D7 applies to bounds
  too: if `[re − a, re + a]` straddles the threshold → `ARTIFACT_PRECISION_COARSER`.
- `delta = re − v` (or `re − m` for a bound), recorded on every bound decision.

## Out of scope

Locating values, run causes, record construction and serialization, per-kind defaults.

## Acceptance criteria (failing tests first)

1. `0.87` vs `0.87` → `REPRODUCED` with `delta = 0`; vs `0.8712` → `REPRODUCED`, band
   `[0.865, 0.875]`; vs `0.875` (boundary) → `REPRODUCED`; vs `0.8751` → `DIVERGED`.
2. `0.870` vs `0.8712` → `DIVERGED` (band `±0.0005`): precision the paper wrote is honoured.
3. `0.87` vs `0.89`, `abs 0.05` → `WITHIN-TOLERANCE`; `rel 0.01` → `DIVERGED`.
4. `rel` tolerance against a reported `0` → `NO_TOLERANCE`.
5. `10,000` (no tolerance) → `PRECISION_AMBIGUOUS`; with `abs 500` vs `10213` →
   `WITHIN-TOLERANCE`; `12` vs `12.4` → `REPRODUCED`.
6. `87%` with no scale → `UNIT_UNDECLARED`; `scale 100` vs located `0.8712` → `REPRODUCED`.
7. D7: paper `0.8712`, located text `0.87` → `ARTIFACT_PRECISION_COARSER`; paper `0.8712`,
   located `0.89` → `DIVERGED`; paper `87.12%`, located `0.87`, scale 100 → coarser (the
   `87.00` exponent trap is pinned).
8. `p < 0.001` vs `0.0004` → `REPRODUCED`; vs `0.0012` → `DIVERGED`; vs `0.001` →
   `ARTIFACT_PRECISION_COARSER` (the run's rounding straddles the threshold); vs `0.0012` with
   `abs 0.0005` → `WITHIN-TOLERANCE`; each `op` covered.
12. (Added at the C2 checkpoint, 2026-09-25.) The coarse-artifact check precedes the band: a
    paper's `0.90` against a run's `0.9` is `ARTIFACT_PRECISION_COARSER`, never `REPRODUCED` —
    the order first implemented made it a false pass.
9. Each unsupported kind → `UNSUPPORTED_VALUE_KIND`.
10. A `float` passed anywhere raises `TypeError` (no silent coercion).
11. Results are identical under a hostile ambient `decimal` context (precision 3, rounding
    `ROUND_FLOOR`) — the pinned local context is load-bearing.

## Dependencies & sequencing

Consumes `plumb.extract.value` only. Independent of `locators`.

## Risks

- R2: D1's closed boundary and D2's "no tolerance → `DIVERGED`" are pinned by criteria 1–2;
  changing either must change a test.
