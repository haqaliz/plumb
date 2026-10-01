# Understanding: value-kinds-compare

Placed in the pipeline: **C4 binding & verdict** — the moat. Verdict-touching work:
comparison is pure code over already-executed, already-located values, so
"execution decides" holds by construction (no model in the compare path; the
bindings stay user-written, D6). Guardrails #1/#3 apply: never a false
`REPRODUCED`, never `DIVERGED` on a harness-side failure.

## What the work really is

C1 already extracts and serializes all six value kinds
(`src/plumb/extract/value.py:101-154`, `serialize.py:180-183`); C3 already runs and
captures; C4's locators already bind. The *only* missing piece is comparison: the
D3 kind gate refuses `PlusMinus`, `Interval`, `Range`, `Approximate` with
`UNSUPPORTED_VALUE_KIND` (`src/plumb/verify/compare.py:115-116`, pinned at
`docs/planning/binding-verdict/prd.md:80-84` D3 and out-of-scope at prd.md:236).

So this slice is: extend `decide()` (`compare.py:98-125`) with one conservative
compare policy per new kind, in the D1-D8 decision style, with tests first. The
D3-decision *and* its out-of-scope note must be rewritten — this feature is the
reversal of a pinned decision, so the PRD must record the replacement decisions
(D9-D12) explicitly rather than quietly editing D3.

## Affected area (from the dig)

- `src/plumb/verify/compare.py` — kind gate (115-116), new `_plus_minus` /
  `_interval` / `_range` / `_approximate` helpers, possibly `Decision` fields
  (84-96), module docstring (9-45, "the contract").
- `src/plumb/verify/__init__.py:41` — docstring table row; evidence mapping in
  `_verify_one` (179-195) if `Decision` grows.
- `src/plumb/verify/causes.py:73-74` — comment; the cause string itself depends on
  the open question below.
- `src/plumb/verify/numbers.py` — `half_unit` reuse for endpoint extension.
- Tests that deliberately assert the old refusal and must be rewritten test-first
  as the new behaviour: `test_compare.py:67-74` (`TestGates`), `test_verify_seam.py:97-103`,
  and the catalogue case `test_cause_catalogue.py:43`.
- Docs: `docs/planning/binding-verdict/prd.md` (D3, out-of-scope), `compare/spec.md`
  criterion 9, `CAPABILITY_ROADMAP.md:178`, `CLAUDE.md:46`.

## Open questions for the PRD (each becomes a D-decision)

1. **PlusMinus policy.** Brief: centre within the paper's written precision *plus*
   its stated margin — i.e. located ∈ `[center − margin − half_unit(center),
   center + margin + half_unit(center)]` → `REPRODUCED`; outside → explicit
   tolerance (D2-style `WITHIN-TOLERANCE`) or `DIVERGED`. Is the margin itself
   precision-extended (the paper wrote 2 digits — is the margin "0.02" or
   `[0.015, 0.025]`)? Conservative default: treat the margin as a written decimal
   with its own half-unit.
2. **Interval/Range policy.** Closed-band membership on `[low, high]`; D1-consistent
   choice is each endpoint extended by its own half-unit. Same policy for both
   kinds (identical fields), or does `Range` get a looser reading ("between")?
   Default: identical, band-extended.
3. **Approximate policy.** "~" means the paper is *not* asserting exact rounding —
   does the written-precision band still apply, or is an explicit tolerance
   required (`NO_TOLERANCE` otherwise)? Conservative default: band = written
   precision of the value, no tolerance required, but the `~` is recorded in the
   evidence.
4. **Does `UNSUPPORTED_VALUE_KIND` survive?** The vocabulary is closed and the
   catalogue test asserts every cause is emitted by a real case
   (`test_cause_catalogue.py:63-64`). After this slice all six kinds are compared,
   so the cause loses its emitter. Options: (a) remove it from `CAUSES` (updates
   catalogue, causes docstring, `verify/__init__.py` table, spec criterion 9) or
   (b) keep it for a residual path (e.g. an unparseable/unknown kind class reaching
   `decide`) with a real catalogue case. Default: (a) — an unemittable cause is
   dead vocabulary; but note `DIVERGED`/`UNVERIFIED` record validation
   (`test_verdict.py:105-108`) enforces the closed set, so the removal must be
   coordinated.
5. **Percentage-points question** (`src/plumb/extract/claim.py:98-100`): out of
   scope here unless the D-decisions force it; state that explicitly.

## Constraints honoured

- Conservative by construction: no false `REPRODUCED` (band extends, never
  shrinks), `DIVERGED` only when the artifact's own run contradicts the claim.
- The false-`DIVERGED` guard is mutation-checked in-suite
  (`test_false_diverged_guard.py`); new kinds must sit inside the same guarded
  flow, not beside it.
- Byte-identical canonical serialization; no floats; pinned `Decimal` context
  (`numbers.py:40-44`, hostile-ambient test at `test_compare.py:267-283`).
- Test-first; no network in tests; bindings remain user-written JSON.