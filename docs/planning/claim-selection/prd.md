# PRD — Claim Selection (C1, aspect 2 part 2)

| | |
|---|---|
| Capability | **C1** — `docs/technical/CAPABILITY_ROADMAP.md:17-30` |
| Phase | Phase 0 — Prove the wedge (`docs/ROADMAP.md:15-27`) |
| Branch | `feat/claim-selection/aliz` |
| Depends on | C1 aspect 1 + aspect 3 + aspect 2 part 1 (all merged on `master`) |
| Blocks | **C4** (the moat) — a claim without a measured selection rule is an unmeasured denominator (`prd.md` parent, `docs/planning/claim-extraction/prd.md:29-34`) |
| Status | Drafted; pending review gate |

Parent: `docs/planning/claim-extraction/prd.md` (M3, M4, M15, M11). Aspect spec:
`docs/planning/claim-extraction/extraction-core/spec.md` (part-2 acceptance
criteria at `spec.md:42-54`). Card: `docs/planning/_card/issue.md`;
understanding: `docs/planning/_card/understanding.md`.

---

## Problem Statement

C1's deterministic spine has landed: candidates are extracted exhaustively, the
admission gate is the sole constructor of a `Claim`, N is a `StudyParameter`, and a
blind-labelling harness emits and reloads human labels. **What does not exist is the
rule that decides which candidates are claims** — the substance of C1
(`CAPABILITY_ROADMAP.md:42`). Today `admit.py:35-38` says it plainly: "This is not
selection… deferred to part 2 so it can be scored against labels it did not author."

Why this is the next unit: the Phase 0 gate number — *what fraction of headline
claims can we bind and re-derive* (`ROADMAP.md:17-18`) — has C1's output as its
denominator (`docs/planning/claim-extraction/prd.md:29-34`). An unmeasured selection
rule means C2–C4 would be built on a denominator that may be inflated (under-
extraction) or buried in `UNVERIFIED` (over-extraction, R1 `ROADMAP.md:56`).
Concretely broken today: the sample-size fall-through class — `n of 412`,
`sample size of 412`, `n₁ = 412`, a table cell `| n | 412 |` — still admits as
`Claim`, landing permanently unbindable numbers in the coverage denominator
(`spec.md:73-90`).

## Goals & Success Metrics

**Goal.** A deterministic selection rule (M3) scored against labels it did not
author (M15), plus a free-text metric namer that produces the named quantity C4's
locators will aim at — with the label commit verifiably *before* the rule commit.

| Metric | Target | Why |
|---|---|---|
| **Ordering** | Filled label commit precedes the rule commit; verifiable in `git log` | The deliverable — M15's circularity guard (`spec.md:42-43`, `prd.md` M15) |
| **Selection precision/recall** | Computed and reported against the 73 blind rows; **no numeric bar** this slice | Honest, not statistically meaningful (single labeller, 5 papers — `prd.md` parent open question 1) |
| **Rejection categories** | One failing-first test each (7 categories + related-work + unnamed-metric) | `spec.md:44-48` |
| **Sample-size fall-through** | `n of 412`, `| n | 412 |` etc. rejected structurally (named-metric test), never enumerated | `spec.md:73-90` |
| **Determinism / network** | Byte-identical output; zero network in tests (inherited) | `ARCHITECTURE.md:137`, `:144` |

Explicitly **not** a goal: a coverage or bind-rate number (needs C3+C4), a
defensible precision bar (needs C5 + third-party labels), a widened heading map.

## User Personas & Scenarios

C1 has no user-facing surface; the consumers are the engine and the owner.

- **The engine (C4, load-bearing persona).** It must be able to write a locator
  against a `Claim` whose `metric` names a real quantity from the paper's own
  sentence — without re-interpreting prose (`ARCHITECTURE.md:83-85`). The metric
  namer is written to that contract: the metric text is *the phrase in the paper*,
  not a classification.
- **The owner (the labeller).** Fills the 73 blind rows now, by hand, per the
  emitter's instructions; their judgement is the measurement instrument. Nothing in
  this unit may suggest a label to them (`labelling.py:11-19`).
- **The scorer.** Precision/recall over the blind rows is the honesty instrument
  for the gate number; `UNVERIFIED`-style hedging is not available — the rule is
  right or wrong per row, and the score says which.

## Requirements

### Must-have

**M1. The filled blind labels are committed before the rule.** The owner's 73-row
pass over `fixtures/labels/*.todo.jsonl` lands as the unit's first commit; the rule
commit comes later. Verifiable in `git log`; stated in the PR.

> **M1 rationale.** M15 (`prd.md` parent). The ordering is the deliverable, not a
> suggestion: precision/recall must measure whether the rule is *right*, not whether
> the code implements its author's idea (`plan_20260921.md:12-20`). Current state:
> 73 data rows, all `"label": null`, all `section: abstract`.

**M2. The selection rule (M3).** A candidate is admitted only if (a) asserted by
*this* paper about its own results, (b) carries a named metric, (c) appears in
abstract, results, or a table. Rejection list, one failing-first test each:
publication/citation years, page/figure/table/equation numbers, version strings,
grant/DOI/ORCID digits, reference-list numerals, hyperparameters, axis labels.
A related-work number attributed to another paper is never this paper's claim
(guardrail `CLAUDE.md` #3, **R4** `ROADMAP.md:59`).

> **M2 rationale.** `spec.md:20-24`. Criterion (c) is implemented as **abstract or
> table** — the heading map matches only 17/119 real headings, two fixture papers
> yield zero `results` candidates, so the rule must not lean on `results`
> (`spec.md:146-157`, understanding §2). Criterion (a) is a context-level test
> (attribution), not a lexical one.

**M3. The rule produces the metric: free-text quantity phrase from context.**
For an admitted candidate, the rule extracts the named quantity from the
candidate's own context (`Candidate.context` — the sentence or cell), e.g.
`sensitivity`, `AUC`, `prevalence estimate`, and passes it to `admit(...,
metric=...)`. A candidate with no identifiable quantity is rejected as unnamed-
metric. **Decision (owner, 2026-09-21): free text, no controlled vocabulary.**

> **M3 rationale.** Criterion (b) requires the rule to *name*, not just detect: the
> gate requires a non-blank metric and C4 aims locators at a named quantity
> (`ARCHITECTURE.md:83-85`, understanding §1). A vocabulary would be a list papers
> outrun — the same trap the N recogniser hit (`spec.md:73-90`). The metric is
> measured by scoring, like everything else.

**M4. Rejections surface with a named cause — a selection-side closed vocabulary.**
The rule's rejections are emitted as non-claim records carrying a cause from a new
closed selection-side set (e.g. `reference_numeral`, `no_named_metric`,
`related_work`, `outside_sections`), **distinct from the gate's** `NON_CLAIM_CAUSES`.
Never a `Claim`, never a verdict, never silent (parent M4, `prd.md:96-98`).

> **M4 rationale.** Precedent: `plan_20260921.md:50-52` — extraction-side causes
> are separate from C4's verdict causes; a cause spelled like a verdict would be
> read as one (`admit.py:30-33`). Selection-side causes are likewise separate from
> the gate's (the gate checks grounding/notation, the rule checks worth).

**M5. The sample-size fall-through class is closed structurally.** `n of 412`,
`sample size of 412`, `n₁ = 412`, table cell `| n | 412 |` must be rejected by the
named-metric requirement — `n` supplies no metric — never by enumerating spellings
(`spec.md:73-90`). N stays a `StudyParameter`, never a `Claim` (parent M11).

**M6. Scoring: precision/recall against the blind rows.** A scoring module computes
precision and recall of the rule's predictions over the 73 labelled rows, joined on
`candidate_id` (`labelling.py:225`); results reported as the slice's headline
output. **No pre-set numeric bar, but a floor on first sight (owner decision,
2026-09-21):** the first computed score is recorded in the PR, and a score below a
floor agreed at that moment forces a rule revision before merge — the slice can
fail. The rule stays provisional regardless — five papers can show it wrong, not
right (`spec.md:68-69`).

**M7. Criterion (c) is unit-test-validated only this slice.** All 73 blind labels
are abstract candidates, so the section filter is never exercised by the score; a
wrong (c) implementation scores identically to a right one. The PR must state this
explicitly: the blind score measures (a) and (b) on abstracts; (c) is validated by
unit tests; widening the labels is a later slice.

**M7. The admission gate stays the sole constructor of a `Claim`.** The rule
selects *before* the gate (reference numerals never reach the gate at all —
`test_admit.py:992-994`); `TestTheGateIsNotTheSelectionRule` keeps passing
(`test_admit.py:913-952`); the gate's `study_parameter` refusal and
`study_parameters` are not re-implemented by the rule.

**M8. Determinism and no-network inherited.** Rule and scoring are deterministic
(shared `ordering` helpers; no `set` iteration, no `hash()`, no timestamps), and no
test touches the network (socket-blocking fixture, `ARCHITECTURE.md:144`).

**M9. End-to-end entry point (promoted from S1 — owner decision, 2026-09-21).**
`extract_claims(raw) -> tuple[Claim | NonClaim, ...]` in `src/plumb/extract/`,
wiring candidates → selection → gate. The seam C4 and `plumb verify` will consume;
without it the rule is only scoreable, not usable.

### Should-have

- **S1.** ~~End-to-end entry point~~ — **promoted to M9** (owner decision,
  2026-09-21).

### Nice-to-have

- **N1.** Report the score in a machine-readable form (e.g. a small JSON summary)
  alongside the human table.

## Technical Considerations

- **Pipeline position.** Head of the intake pipeline: candidates (`extract_candidates`,
  candidates.py:510) → **selection (new `selection.py`)** → gate (`admit`,
  admit.py:338) → `Claim`/`NonClaim`. Scoring (new module, e.g. `scoring.py`) reads
  `load_labels` output (`labelling.py:561`) joined on `candidate_id`.
- **Layout.** `src/plumb/extract/selection.py` (+ `scoring.py`), tests at
  `tests/extract/test_selection.py`, `tests/extract/test_scoring.py`. No CLI this
  slice (parent N1 — no design doc specifies one beyond `plumb verify`).
- **The rule reads `Candidate.section_hint`** for criterion (c) — the gate reads it
  not at all (admit.py:38), so this is the first consumer. `table`-hint candidates
  are in scope for (c); `references` and `other` are out.
- **The metric namer works on the candidate's own text and context** — the verbatim
  sentence, the same bytes the offsets index; nothing outside the paper is consulted.
- **Verdict impact: none.** C1 emits no verdicts; the rule's output is
  `Claim`/`NonClaim`, never `REPRODUCED`/`DIVERGED`/`UNVERIFIED` (`prd.md` parent:
  206-209). The selection-side causes are deliberately spelled unlike verdicts.
- **Known recall gaps score honestly**: ASCII-hyphen ranges (`12-15`) and units
  coupling (`0.87 kg`) remain open and surface in the blind score rather than being
  guessed at (`spec.md:161-176`).

## Risks & Open Questions

| Risk | Ref | Mitigation in this PRD |
|---|---|---|
| **Claim-extraction error** — a wrong selection rule | **R3** Med/High, `ROADMAP.md:58` | M1 ordering; M6 scoring; M5 structural fix; every rejection category has a failing-first test |
| **Binding coverage** — over/under-extraction distorts the gate denominator | **R1** High/High, `ROADMAP.md:56` | M6's honest score is the instrument; no bar means no self-congratulation; provisionality stated |
| **Legal/ethical** — a related-work number attributed to this paper | **R4** Med/High, `ROADMAP.md:59` | M2's criterion (a): context-level attribution test, failing-first |
| **Circularity** — the rule author labelling their own fixture | M15 | M1: the owner's label commit precedes and is disjoint from the rule commit; the emitter never suggests labels |

**Open questions.**

1. **The rule is provisional after this slice** — five blind papers can show it
   wrong, they cannot show it right (`spec.md:68-69`). Expect revision at the first
   real corpus run.
2. **`ROADMAP.md:58` still phrases R3's mitigation as "`UNVERIFIED` when the claim
   can't be grounded"** — resolved for C1 by parent M4 (non-claim with named cause);
   the ROADMAP amendment is a doc follow-up, not this unit's job.
3. **The card's "~84 rows" is stale** — composite regeneration left 73; the scorer
   counts whatever `load_labels` accepts (it refuses missing rows).
4. Whether criterion (a)'s attribution test needs the *previous sentence* or only
   `context_before`/`context_after` — decide in tech-plan; the fixture rows carry
   both, so the data supports either.

---

## Areas to strengthen before sharing (self-critique)

| Dimension | Rating | Note |
|---|---|---|
| Problem definition | 🟢 | Grounded in the unbuilt substance of C1 and a measured fall-through class |
| User understanding | 🟢 | C4/owner/scorer contracts are explicit; no external users claimed |
| Success metrics | 🟡 | "Reported" without a bar is not falsifiable (G1 below) |
| Scope clarity | 🟡 | S1 in-or-out undecided (G3) |
| Edge cases & risks | 🟡 | The blind set cannot measure criterion (c) (G2) |
| Stakeholder alignment | 🟢 | Solo owner is labeller and approver |
| Feasibility | 🟢 | Seams mapped (selection.py + scoring.py; `admit`, `load_labels`); no new deps |
| Verdict honesty | 🟢 | No verdicts emitted; selection causes distinct from verdicts; gate stays sole constructor |

**G1 🟡 — No falsifiable bar (metrics).** "Computed and reported" with no floor
means the slice cannot fail: any score is a baseline. **Resolved at the gate
(2026-09-21):** floor set on first sight; below it, revision before merge. Now M6.

**G2 🟡 — Criterion (c) is unmeasurable by the blind set (edge cases).** All 73
labels are abstract candidates, so the section filter is never exercised by the
score — a wrong (c) implementation scores the same as a right one. **Resolved at
the gate:** (c) is unit-test-validated only, stated in the PR. Now M7.

**G3 🟡 — S1 in-or-out (scope).** The end-to-end entry point decides whether the
metric namer is engine-usable or test-only. **Resolved at the gate:** promoted to
must-have. Now M9.

**The question I'd want answered before greenlighting this:** if the rule scores
100% precision and 40% recall on the blind set, what happens — merge, revise, or
is the number itself the deliverable? If every score is acceptable, what
observable result would make this slice a failure rather than a baseline?

## Out of Scope

- PDF → text, DOI resolution, the BYOK proposer (later C1 slices).
- Widening the heading map (`results` stays unreliable; criterion (c) is
  abstract-or-table).
- A controlled metric vocabulary (rejected, Q2).
- A numeric precision/recall bar, coverage/bind-rate numbers (need C2–C5).
- Any verdict vocabulary, any `UNVERIFIED` cause, anything in C2–C8.
- Amendments to `ROADMAP.md` / parent PRD follow-ups (tracked separately).