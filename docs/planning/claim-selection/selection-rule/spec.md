# Aspect — `selection-rule`

Parent: [`../prd.md`](../prd.md) · Covers **M1–M9** · Depends on: C1 aspects 1, 3,
and aspect 2 part 1 (all merged) · Branch `feat/claim-selection/aliz`.

## Problem slice

The rule that decides which of a paper's candidates are claims — the substance of
C1 (`CAPABILITY_ROADMAP.md:42`) — plus the scoring that measures it against labels
the rule did not author (M15). Also closes the sample-size fall-through class
structurally (`extraction-core/spec.md:73-90`) and produces the named metric C4's
locators will aim at.

**Outcome:** a deterministic `select` + `extract_claims` pipeline whose
precision/recall over the 73 blind rows is computed, reported, and floored.

## In scope

1. **Label commit first (M1).** The owner's filled 73 rows committed before the
   rule; verifiable in `git log`.
2. **Selection rule (M2).** (a) own-results assertion (related-work rejection),
   (b) named metric, (c) abstract-or-table (results is unreliable; `references` →
   reference numerals; `other` → rejected). One failing-first test per rejection
   category: year, figure number, version string, DOI digits, reference-list
   numeral, hyperparameter, axis label — plus related-work and outside-sections.
3. **Metric namer (M3).** Free-text quantity phrase from `Candidate.context`;
   no identifiable quantity → `no_named_metric`. Free text, no vocabulary
   (owner decision).
4. **Selection-side causes (M4).** New closed `SELECTION_CAUSES` vocabulary,
   distinct from the gate's `NON_CLAIM_CAUSES`; rejections surface as
   `SelectionRejection` records — never silent, never a `Claim`, never a verdict.
5. **Structural N closure (M5).** `n of 412`, `| n | 412 |` etc. rejected by the
   named-metric requirement, never enumerated. N stays `StudyParameter`.
6. **Scoring (M6).** Precision/recall over the blind rows joined on
   `candidate_id`; pooled + per-paper; floor set on first sight
   (owner decision): below-floor score forces rule revision before merge.
7. **Criterion (c) is unit-test-validated only (M7).** The blind set cannot
   measure it; stated in the PR.
8. **End-to-end entry point (M9).** `extract_claims(raw)` wiring candidates →
   selection → gate.

## Out of scope

PDF, DOI, the BYOK proposer; widening the heading map; a metric vocabulary;
`parse_value`/units parsing changes (value.py untouched); any verdict vocabulary;
anything in C2–C8.

## Acceptance criteria (failing tests first)

- **Ordering:** the filled-label commit precedes the rule commit (verifiable in
  `git log`; stated in the PR).
- One failing-first test per rejection category asserting the number is **not**
  emitted as a claim: publication year, figure number, version string, DOI digit
  sequence, reference-list numeral, hyperparameter, axis label.
- A related-work number attributed to another paper is **not** emitted as this
  paper's claim (R4).
- `n of 412` and a table cell `| n | 412 |` are **not** claims — closed
  structurally, with no per-spelling enumeration in the rule.
- Every rejection surfaces as a `SelectionRejection` with a cause from the closed
  `SELECTION_CAUSES` set — asserted positively.
- No `Claim` bypasses the admission gate; `TestTheGateIsNotTheSelectionRule` and
  the AST sole-constructor test keep passing.
- Every admitted `Claim` carries a non-empty `metric` (free-text quantity phrase
  from the paper's own context).
- `extract_claims(raw)` returns claims + rejections; the five fixture papers run
  end-to-end deterministically.
- Scoring computes pooled precision/recall over the 73 blind rows; the floor test
  asserts pooled precision ≥ floor and pooled recall ≥ floor (floor named as a
  constant, value set at first sight); the PR records the score and the floor.

## Dependencies and sequencing

Phase 0 (labels) blocks everything. Scoring (Phase 1) is independent of the rule
and can be built first. Selection (Phase 2) is the risky core. Wiring (Phase 3)
and blind scoring (Phase 4) consume Phases 1–2.

## Risks

- **R3** (Med/High) — this aspect *is* R3; M15's ordering is the mitigation.
- **R1** (High/High) — over/under-extraction distorts the gate denominator; the
  honest score is the instrument.
- **R4** (Med/High) — the related-work rejection is the legal/ethical guard.
- Heuristic quality: the rule's context cues are provisional closed lists; the
  blind score measures (a)+(b) on abstracts, unit tests cover the rest.

## Open questions

- Whether `Candidate` exposes column/row context for table cells (for the metric
  namer) — the implementing agent checks `candidates.py` first.
- Exact noise-word/function-word list for the metric namer — fixed in the plan,
  provisional by design.