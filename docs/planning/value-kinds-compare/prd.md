# PRD: value-kinds-compare

Slice: C4 compare extension — decide `PlusMinus`, `Interval`, `Range`, `Approximate`
claims instead of refusing them with `UNSUPPORTED_VALUE_KIND`.

## Problem Statement

C4's first slice deliberately compared only `Point` and `Bound`; the other four value
kinds that C1 already extracts and serializes (`src/plumb/extract/value.py:101-154`,
`serialize.py:180-183`) are refused by the D3 kind gate
(`src/plumb/verify/compare.py:115-116`) as `UNSUPPORTED_VALUE_KIND`
(`docs/planning/binding-verdict/prd.md:80-84`, out-of-scope at prd.md:236). Real
papers write headline claims overwhelmingly as `±`/CI/range/`~` — the Phase 0 gate
passed on one curated paper (`docs/ROADMAP.md:29-33`), and Phase 1's remaining work
is cross-paper coverage, risk R1 (High/High, `docs/ROADMAP.md:67-68`). Every such
claim on the next real paper will be refused before comparison, stalling coverage
at the compare step rather than at binding. The record layer is done; only the
compare is missing.

## Goals & Success Metrics

- **G1 — Every value kind decides.** A claim of any of the six kinds, bound to a
  fresh artifact value, yields a verdict: `REPRODUCED`, `WITHIN-TOLERANCE`,
  `DIVERGED`, or `UNVERIFIED` with a named cause. No claim is refused for being a
  `PlusMinus`/`Interval`/`Range`/`Approximate`.
- **G2 — No false `DIVERGED`, no false `REPRODUCED`.** Band semantics are pinned
  conservatively (D9–D11); the D7 coarse-artifact protection extends to band kinds
  (D13); the mutation-checked false-`DIVERGED` guard keeps governing every claim.
- **G3 — Closed vocabulary stays exact.** Removing `UNSUPPORTED_VALUE_KIND` is a
  coordinated change (catalogue, causes, docstrings, spec criteria); the
  catalogue/union and verdict-record closed-set tests keep passing.
- **G4 — Determinism & offline.** Canonical byte-identical serialization, pinned
  `Decimal` context, no floats, no network — per the C4 contract.

Metric is conformance, not coverage: every acceptance criterion is a failing test
first. Real-paper coverage is the next gate paper's job (out of scope).

## User Personas & Scenarios

- **A reviewer/lab** binds a headline claim written `0.87 ± 0.02`, `95% CI [0.81,
  0.93]`, `12–15%`, or `~0.87` and gets a decided verdict with the band that
  decided it — instead of `UNVERIFIED: UNSUPPORTED_VALUE_KIND`.
- **The founder, hardening against real repos (R1)**, sees the honest number on a
  new paper without a giant refused-kinds bucket dominating it.

## Decisions (owner-accepted, 2026-10-01)

These **supersede D3** (`docs/planning/binding-verdict/prd.md:80-84`) and its
out-of-scope line (prd.md:236). D1–D2, D4–D8 stand unchanged and are referenced by
number. The written-precision philosophy of D1 governs every band: the digits the
paper wrote are the claim, so every boundary is a written decimal with its own
half-unit.

- **D9 — `PlusMinus` is decided by its centre, band widened by its margin.** The
  reported claim is `center ± margin`. Decision band:
  `[center − margin − hc − hm, center + margin + hc + hm]`, closed, where
  `hc = half_unit(center)` and `hm = half_unit(margin)` — the margin is itself a
  written decimal and gets D1's half-unit treatment. Inside → `REPRODUCED`
  (evidence records the band). An explicit tolerance (D2) widens → `WITHIN-TOLERANCE`.
  Outside both → `DIVERGED`. `margin = 0` degenerates to the D1 `Point` band and is
  allowed. D1a applies to the centre (a trailing-zero-integer centre with no
  tolerance is `PRECISION_AMBIGUOUS`); the margin is a width, not a claim value,
  so D1a does not apply to it.
- **D10 — `Interval` and `Range` are decided by closed-band membership, endpoints
  extended.** Structurally identical (`low`, `high`), one policy. Decision band:
  `[low − hl, high + hh]`, closed, with `hl = half_unit(low)`, `hh = half_unit(high)`.
  Inside → `REPRODUCED`; tolerance widens → `WITHIN-TOLERANCE`; outside both →
  `DIVERGED`. D1a does **not** apply to endpoints: an endpoint's rounding is the
  band's fuzz (the paper wrote `20`, so `20.4` is inside its rounding of the
  boundary), not an ambiguous claim value.
- **D11 — `Approximate` is decided exactly like a `Point`.** `~` is prose: the
  paper's number is the written digits, band = D1 closed half-unit band on the
  value; tolerance widens; outside both → `DIVERGED`. The `~` is recorded in the
  evidence (provenance), never a wider band and never a refusal.
- **D12 — `UNSUPPORTED_VALUE_KIND` is removed from the closed vocabulary.** All six
  kinds now compare; an unemittable cause is dead vocabulary. One coordinated
  change: `plumb/verify/causes.py` (constant, docstring, `CAUSES`),
  `plumb/verify/__init__.py` (cause table), the catalogue
  (`tests/verify/test_cause_catalogue.py` — the union assertion keeps passing with
  the smaller exact set), the verdict-record closed-set check
  (`tests/verify/test_verdict.py`), and `docs/planning/binding-verdict/compare/
  spec.md` criterion 9.
- **D13 — D7's coarse-artifact protection extends to band kinds.** For a
  `PlusMinus`/`Interval`/`Range`/`Approximate` located **outside** its decision
  band: if the artifact wrote fewer digits than the nearest band boundary's written
  precision and the located value is within the artifact's own half-unit of that
  boundary, the verdict is `UNVERIFIED: ARTIFACT_PRECISION_COARSER` — the artifact
  cannot resolve the boundary; else `DIVERGED` stands. This is D7's "can the
  artifact's own writing reach the paper's claim" generalized from a point to a
  band. **Inside the band, no coarseness check applies for `PlusMinus`/
  `Interval`/`Range`:** the band is the claim's resolution, and a located value
  inside it is within the paper's own written fuzz — no false `REPRODUCED` is
  possible. `Approximate` is a `Point` and keeps D7's point rule in full, inside
  or outside. The scaled half-unit trap (D7: half-unit × `scale`, never the scaled
  product's exponent) applies to every boundary in percent claims (D4 parity).

## Requirements

### Must-have

**M1 — `PlusMinus` compare** per D9, on `Decimal` components (`center`, `margin`),
in the pinned context, with D4 `scale` parity (centre and margin scale; scaled
half-units per D7's trap pin). Returns `REPRODUCED` / `WITHIN-TOLERANCE` /
`DIVERGED` / `UNVERIFIED` with the deciding band in the evidence.

**M2 — `Interval`/`Range` compare** per D10, same policy for both kinds, `scale`
parity included.

**M3 — `Approximate` compare** per D11 — D1/D2 parity; `~` recorded in evidence.

**M4 — D13 coarse-artifact check** for all four kinds, before any band/tolerance
decision, in the D7 position of the decision order.

**M5 — Closed vocabulary update** per D12, coordinated across causes, tables,
catalogue, verdict-record validation and specs — the union test
(`test_cause_catalogue.py`) and the record closed-set test (`test_verdict.py`)
stay exact with the smaller set.

**M6 — Guarded flow.** All new decisions flow through the existing run-cause
precedence and the mutation-checked false-`DIVERGED` guard
(`tests/verify/test_false_diverged_guard.py`) — no bypass, no new harness-side
`DIVERGED` path.

**M7 — Test-first rewrites.** The three tests asserting the old refusal become
failing tests for the new behaviour before any production change:
`tests/verify/test_compare.py` (`TestGates.test_value_kinds_this_slice_does_not_
compare`, lines 67-74), `tests/verify/test_verify_seam.py` (lines 97-103),
`tests/verify/test_cause_catalogue.py` (the `UNSUPPORTED_VALUE_KIND` case, line 43).

**M8 — Evidence & serialization.** Decisions carry the deciding band in the
**existing** `Decision.band` fields (`compare.py:84-96`) — no record-format
change; the `~` provenance is the claim's own reported text, already in the
record; canonical serialization stays byte-identical; committed records
(AgroDesign) and bundles are untouched by construction.

**M9 — Docs.** `compare.py` module docstring (the contract), the D3 record in
`docs/planning/binding-verdict/prd.md` (marked superseded, referencing D9–D13),
`CAPABILITY_ROADMAP.md:178`, `CLAUDE.md:46`, and `compare/spec.md` criterion 9.

### Should-have

- A hostile-ambient `Decimal` context test for one band kind (D9 or D10), mirroring
  `TestPinnedContext` (`test_compare.py:267-283`).

### Nice-to-have

- None.

## Technical Considerations

- All inputs already exist: parsed kinds (`value.py`), tags (`serialize.py:180-183`),
  `half_unit` (`verify/numbers.py:64-66`), the pinned `CONTEXT` (`numbers.py:40-44`),
  the `Decision` record (`compare.py:84-96`).
- `Decision` may gain band fields; `_verify_one`'s evidence mapping
  (`verify/__init__.py:179-195`) is the only other production touch-point.
- No new dependencies. No network. No floats.

## Risks & Open Questions

- **R2-adjacent — pinned semantics, revisited on evidence.** D9–D11 and D13's
  boundary rule are exactly the class of choices D1–D8 pinned and revisited only
  with gate-paper evidence (`binding-verdict/prd.md` Risks). The next real paper
  may show a paper-specific quirk; the decisions stand until it does.
- **D13 is the subtlest rule.** "Nearest boundary, artifact's own half-unit"
  needs the scaled-half-unit trap pin (a `95% CI [0.80, 0.93]` percent claim
  against a `0.81` artifact etc.) and a mutation-style test that loosening it
  produces a false `DIVERGED`.
- **`%` vs percentage points stays open** (`src/plumb/extract/claim.py:98-100`,
  `binding-verdict/prd.md` Risks) — untouched by this slice, stated so it isn't
  silently forgotten.
- **Open — malformed kinds reaching `decide`.** Does C1's parse guarantee `margin >
  0` and `low ≤ high` (negative margins, reversed intervals)? The dig did not
  confirm. If the admission gate guarantees well-formed kinds, compare needs no
  defence; if not, pin a compare-side refusal cause. Resolved in the spec.
- **Open — D13's nearest-boundary choice when the artifact is coarser than both
  boundaries** (e.g. one-digit artifact vs `[0.81, 0.93]`): the nearest boundary
  decides. Pinned in D13; a mutation-style test must prove loosening it produces
  a false `DIVERGED`.

## Out of Scope

- The binding proposer (`PROPOSER_UNGROUNDED`/`MODEL_ONLY_SIGNAL` stay reserved).
- Notebook-cell locators and C3 notebook capture.
- `%` vs percentage-points unit rule.
- Choosing or running the next real paper (cross-paper coverage, R1).
- Per-kind default tolerances (D2: tolerance is explicit, on the binding).