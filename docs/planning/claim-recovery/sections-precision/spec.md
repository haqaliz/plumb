# Aspect spec — `sections-precision`

Parent: `docs/planning/claim-recovery/prd.md` (M1–M5, M2's measure).

## Problem slice

Make AgroDesign's §4 a results section, and refuse the non-claims that exposes, before any
table work. After this aspect, recall is ≥ 0.95 by the D2 match and no dangerous claim
(`¡ 0.001` as a Point) is emitted.

## In scope

- `"experimental validation"` → `results` in `_HEADING_SECTIONS` (literal, tested).
- Gate: `¡`/`¿` directly before a number (spaces allowed) → `partial_value`
  (`admit._is_a_fragment` or a sibling check in the same slot).
- Selection: new cause `layout_numeral` in `SELECTION_CAUSES` — heading numbering prefix,
  whole-line bare integer, line-leading list marker; placed after the section check.
- Selection: `α`/`alpha`/`significance level` join `_HYPERPARAM_CUES`.
- A recovery helper for tests: curated entries vs emitted claims by D2 (location within the
  curated span and equal `ClaimValue`), reporting misses with causes.

## Out of scope

- Table recognition and table metrics (aspect `whitespace-tables`).
- Converter changes; any change to curated fixtures or the bundle.

## Acceptance criteria (tests written first)

1. `_heading_hints` maps `# 4 Experimental Validation` to `results`, and its sub-headings
   inherit it; `## 4. Experimental Setup` stays `other`.
2. `admit` refuses `0.001` in `p ¡ 0.001` and in `x ¿ 3` as `partial_value`; `p < 0.001`
   is unchanged.
3. `select` refuses with `layout_numeral`: the `4.1` of `## 4.1 Completely Randomized`,
   a line `8` alone, the `1` of `1. Correct identification`. It does **not** refuse
   `0.87` in `## Results` body text, nor a table row's leading value.
4. `select` refuses `0.05` in `groupings atα= 0.05` as `hyperparameter`.
5. `SELECTION_CAUSES` and `NON_CLAIM_CAUSES` stay disjoint; the catalogue/vocabulary tests
   list `layout_numeral`.
6. AgroDesign: recall ≥ 0.95 (D2), zero claims whose value text follows `¡`/`¿`, and every
   emitted non-table claim matches a curated claim.
7. No regression: blind score 1.0/1.0, the five fixture floors, the PDF↔Markdown seam, and
   the AgroDesign bundle verification test.
