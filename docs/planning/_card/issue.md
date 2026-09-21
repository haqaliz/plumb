# feat claim-selection — C1 aspect 2 part 2: claim-selection rule + blind scoring

| Field | Value |
|---|---|
| Type | `feat` |
| Id / slug | `claim-selection` |
| Branch | `feat/claim-selection/aliz` |
| Worktree | `.claude/worktrees/feat-claim-selection` |
| Base | `origin/master` @ `c95220d` |
| Owner | aliz |
| Capability | **C1** — `docs/technical/CAPABILITY_ROADMAP.md:17-30` |
| Phase | **Phase 0 — Prove the wedge** (`docs/ROADMAP.md:21`) |
| Source | Inline brief (no GitHub issue — `gh issue view claim-selection` → FALLBACK; tracker is empty) |

## Source note

The brief below is the handoff produced by the `plumb-next` skill earlier in this
session; it is the single source the rest of the pipeline reads from. The parent PRD
(`docs/planning/claim-extraction/prd.md`), the aspect spec
(`docs/planning/claim-extraction/extraction-core/spec.md`), and the part-1 plan
(`docs/planning/claim-extraction/extraction-core/plan_20260921.md` §0) already define
this unit's requirements; this card carries the handoff and the open decisions.

## Brief

> Build C1 aspect-2 part-2: the claim-selection rule (M3) and its scoring against the
> blind labels (M15), per `docs/planning/claim-extraction/extraction-core/spec.md` and
> `plan_20260921.md` §0. First the owner fills the ~84 label rows in
> `fixtures/labels/*.todo.jsonl` (that commit MUST precede the rule commit — the
> ordering is the deliverable and is checked in git log), then the selection rule is
> authored: a number is a claim only if (a) asserted by this paper about its own
> results, (b) carries a named metric, (c) appears in abstract, results, or a table —
> one failing-first test per rejection category (years, figure numbers, version
> strings, DOI digits, reference-list numerals, hyperparameters, axis labels), a
> related-work number never emitted as this paper's claim (R4), and the sample-size
> fall-through class closed structurally via the named-metric test, not enumerated.
> The rule must not lean on the `results` heading hint — the map matches only 17/119
> real headings, so criterion (c) reads "abstract or table" in practice. Report
> precision/recall against the blind fixtures as the slice's headline output, plus
> named-cause non-claims (M4). Acceptance: ordering verifiable in git log; every
> rejection category asserted not-a-claim; no Claim bypassing the admission gate; N
> always StudyParameter, never Claim; precision/recall computed and reported.

## Carried caveats

1. **M15 ordering is the deliverable.** The filled labels must be committed before
   the rule commit; verifiable in `git log` (`extraction-core/spec.md` acceptance
   criteria). If the owner fills labels inside this unit of work, the label commit
   and the rule commit are separate commits, in that order.
2. **The `results` section hint is unreliable.** The heading map matches only 17 of
   119 real headings; two fixture papers yield zero `results` candidates
   (`extraction-core/spec.md` "Known limits"). Criterion (c) effectively reads
   "abstract or table".
3. **The sample-size fall-through class** (`n of 412`, `sample size of 412`,
   `n₁ = 412`, table cell `| n | 412 |`) must be closed structurally by the
   named-metric requirement, not enumerated.
4. **R3** (`docs/ROADMAP.md:58`) is the risk this unit retires; **R1**
   (`ROADMAP.md:56`) is the one it must not worsen (over-extraction buries claims in
   `UNVERIFIED`; under-extraction inflates coverage).

## Linked issues / PRs

None — tracker is empty.

## Comments

None.