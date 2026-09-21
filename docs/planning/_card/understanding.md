# Phase 2 — Understanding: C1 claim-selection (aspect 2, part 2)

Synthesized from two parallel agent digs over the planning docs, the code under
`src/plumb/extract/`, and the fixtures (branch `feat/claim-selection/aliz`).

## Where this sits

**C1** (`CAPABILITY_ROADMAP.md:17-30`), the aspect-2 part-2 that the part-1 plan
(`plan_20260921.md` §0) deferred: **M3 the selection rule** and **M15 scoring against
the blind labels**. The parent PRD (`prd.md`), aspect spec (`spec.md`), and this
worktree's card (`issue.md`) already define the requirements; this unit writes the
rule and the scoring, in that order, after the owner's labels.

## What exists today (the seams the rule plugs into)

- **`extract_candidates(raw) -> tuple[Candidate, ...]`** (candidates.py:510) — the
  exhaustive, judgement-free harness. `Candidate` = `text` (verbatim, composite
  notation whole), `span`, `context` (sentence or cell), `section_hint` ∈
  `{abstract, results, table, references, other}` (candidates.py:278-303).
- **`admit(candidate, *, normalized_text, metric, units, ...) -> Claim | NonClaim`**
  (admit.py:338) — the sole constructor of `Claim` (enforced by AST test).
  `NonClaim` causes (closed): `ungrounded`, `partial_value`, `study_parameter`,
  `unnamed_metric`, `unparsed_value` (admit.py:76-112). The gate reads
  `section_hint` not at all; its docstring says "This is not selection" (admit.py:35-38).
  The gate has no idea what "a metric" is beyond non-blank — **naming the metric is
  this unit's job** (a claim must carry a named quantity so C4 can aim a locator at it).
- **`emit_labelling_file` / `load_labels` -> `LabelledCandidate(row_id, candidate,
  label)`** (labelling.py:451, 561) — label ∈ `{claim, not-claim}`, rows keyed by
  `candidate_id`; loader refuses missing/unlabelled rows (a smaller denominator is
  not a passing score, labelling.py:628-634).
- **`study_parameters(raw)`** (admit.py:433) — recognised N spellings only; the
  fall-through class (`n of 412`, `| n | 412 |`) is structurally closed by M3's
  named-metric requirement, not enumerated (spec.md:73-90).
- **No `selection.py`, no scoring module, no scoring code exists anywhere** — both
  are new modules. `TestTheGateIsNotTheSelectionRule` (test_admit.py:913-952)
  pins the gate admitting years/figure numbers/axis labels — the rule must reject
  these *before* the gate ("reference numerals… from reaching the gate at all (M3)",
  test_admit.py:992-994), not by changing the gate.

## The ordering deliverable (M15)

Labels committed **before** the rule commit; verifiable in `git log` (spec.md:42-43,
plan_20260921.md §0, prd.md M15, enforced in labelling.py:11-19). Current label
state: **73 rows across 5 files, all `"label": null`, all `section: abstract`**
(abstracts only, per fixtures/papers/README.md:42-48). The card's "~84" is stale —
composite-candidate regeneration dropped 6 rows from PMC13134363; the real count is
73. `load_labels` rejects the files as-is until filled.

**Who fills the labels matters.** The circularity M15 exists to prevent is the rule
author labelling their own fixture. The owner (the human) fills the 73 rows; an
agent filling them and then writing the rule would re-open the same hole in a
thinner disguise. The pipeline stops for that human pass.

## Open questions the rule author must decide (from spec.md / prd.md)

1. **Named metric: controlled vocabulary vs free text** (spec.md:70-71). Criterion
   (b) and the structural N-fix both turn on this. The metric also must be
   *produced* by the rule (from `Candidate.context`), since `admit` requires it —
   this unit writes the metric namer, not just a pass/reject filter.
2. **Criterion (c) without `results`.** Heading map matches 17/119; two papers have
   zero `results` candidates (spec.md:146-157). The rule must not lean on
   `results`; in practice (c) reads "abstract or table".
3. **Rejection taxonomy.** The seven rejection categories (year, figure number,
   version string, DOI digits, reference-list numeral, hyperparameter, axis label)
   need a shape — rule-side causes (new, extraction-side vocabulary) vs folding
   into the gate's existing causes. Related-work attribution (R4) is a
   context-level test, not a lexical one.
4. **Scoring shape.** precision/recall over the 73 blind rows; join on
   `candidate_id`; report-only, **no numeric bar** (prd.md:221-224); rule stays
   provisional (five papers can show it wrong, not right).
5. **Known recall gaps surface in scoring, by design**: ASCII-hyphen ranges
   (spec.md:161-169) and units coupling (spec.md:170-173) are left to be measured,
   not guessed.

## Contradictions surfaced (flag, don't paper over)

- `issue.md` says "~84 label rows"; actual files hold **73**. Brief predates the
  composite regeneration (`2be6d64`).
- `ROADMAP.md:58` still phrases R3's mitigation as "`UNVERIFIED` when the claim
  can't be grounded"; M4 resolved this to a **non-claim record with a named cause**
  (prd.md:100-105). ROADMAP amendment is a follow-up, not this unit's job.

## Guardrails this unit touches

- **#1 / #3**: the rule is deterministic; it never emits a verdict, and a
  related-work number must never become this paper's `Claim` (R4).
- **#4**: the deterministic rule (not a model) is exactly the part that gets better
  as models improve — the proposer seam (the gate) stays the sole constructor.
- **#7**: test-first; acceptance criteria at spec.md:42-54 are the failing tests.