---
name: plumb-next
description: Use when deciding what to build next in Plumb and you want the single highest-leverage capability picked from the repo's own roadmap and planning files (not invented), grounded in the moat and in what has already shipped or been deferred, ending with a ready-to-run handoff. Triggers on "plumb-next", "pn", "what's next", "next feature", "pick next".
arguments: ""
---

# Plumb Next (pick the most important capability)

## Overview

Read the repo's own roadmap and planning files, rank the real candidate capabilities
against the moat and against what has shipped or been deferred, and recommend the
single highest-leverage one to build next. End with a ready-to-paste
`plumb-begin-fast` invocation so the next session can start that worktree.

This skill RECOMMENDS and hands off. It does NOT create a worktree or start
`plumb-begin-fast` itself; the user runs the handoff prompt when ready.

## When to use

- "what should I build next", "pick the next capability", at the start of a session.
- After a merged capability or a phase gate, when choosing the next unit of work.
- Not for: executing a chosen capability (use `plumb-begin-fast`), or planning an
  already-chosen one (use `prd-interview` / `tech-plan`).

## The candidate set is the FILES, never invented

Read these (the source of truth, in this order). Plumb is **greenfield**, so the
planning docs carry almost all the signal today — but code, once it exists, wins
over prose:

- `docs/technical/CAPABILITY_ROADMAP.md`: the **C1..C8** engine capabilities in build
  order, each with what it does, why it matters, its dependencies, and its guardrail
  tie-in. This is the primary candidate set.
- `docs/ROADMAP.md`: the phases (0–3), the gates between them, and the **R1..R7 risk
  register**. A candidate that retires a High-likelihood/High-impact risk is worth more
  than its slot suggests.
- `CLAUDE.md` and `VISION.md`: the wedge, the moat, and the guardrails the pick must obey.
- `docs/technical/ARCHITECTURE.md`: the intake → run → re-derive → verdict → bundle design.
- `docs/planning/*/`: in-flight, completed, and DEFERRED work, once any exists. Read the
  understanding/PRD notes: a capability deferred for a real blocker must not be
  re-recommended as if it were a quick win.
- `git log` / `git tag` / the test suite: what actually shipped. Trust this over prose;
  code runs ahead of the narrative docs. **Today there are no commits beyond the
  scaffold** — say so plainly rather than implying shipped state.
- A `CHANGELOG.md` if one ever exists (it does not today).

If a file above is missing, still reference it by path and say it isn't written yet.
Never substitute memory for a file you couldn't read.

## How to rank (grounded in CLAUDE.md)

1. **Execution-grounded verification only.** Intake / run / re-derive / verdict / corpus /
   bundle. Never a bare LLM judge that opines on correctness, never anything requiring
   raw-data egress or credentials the founder lacks. Drop any candidate that violates a
   guardrail.
2. **Respect the build order and its dependencies.** C1..C8 are sequenced and most are
   hard-blocked (C3 needs C2; C4 needs C1+C3; C5/C6 need C4; C8 needs C4+C5+C6). The next
   capability is usually the lowest unshipped ID whose dependencies are met. Recommending
   C5 while C4 is unbuilt is not ambition, it's a blocked pick.
3. **Deepen the moat and compound the corpus.** Favor work that hardens the deterministic
   spine and that gets *better* as base models improve. Every capability should feed the
   discrepancy corpus (C5) wherever feasible.
4. **Protect the critical path. C4 (binding & verdict) is the moat, and it is risk R1/R2:
   High/High.** C5/C6/C8 all block on it. Slipping it slips everything. Weight it
   accordingly.
5. **Never cut the deterministic spine to reach the LLM assist.** The optional BYOK
   proposer in C1 is a supplement; the deterministic core (intake, run, re-derive, bundle)
   ships first and never gets cut for it.
6. **The gate beats the feature.** Before the Phase 0 gate, the highest-leverage work is
   whatever produces *the number* (what fraction of headline claims we can bind and
   re-derive, and how many DIVERGE, with an honest false-positive bar). Building past a
   gate that hasn't been cleared is out of order.
7. **Follow-on slices count.** A shipped capability's next slice (e.g. a second locator
   type once the seam is earned) is a valid candidate.
8. **Demand-pull beats push.** A surface a design partner (a journal, a lab, a reviewer)
   asked for outranks one the roadmap merely lists.

## Process

1. Read the files above. Build the candidate list: unshipped capabilities whose
   dependencies are met, follow-on slices of shipped ones, and any demand-pulled work.
   For thoroughness, you may dispatch one read-only agent to summarize the planning docs.
2. For each candidate, record: shipped-state (cite the file), dependency status,
   moat-leverage, the risk it retires or exposes (by R-id), and any known blocker.
3. Rank by the rules above. Pick ONE, plus one or two alternates.
4. Sanity-check the pick against the guardrails and against the current phase gate.
5. Produce the handoff (below).

## Output format

- **The pick**: one line naming the capability (with its C-id) and a kebab-case slug.
- **Why**: 2 to 3 bullets tying it to the moat, its dependencies, and what shipped — each
  citing a file.
- **Alternates**: one or two lines.
- **Known caveat**: the nearest feasibility risk (name the R-id where one applies), stated
  honestly, so the `plumb-begin-fast` dig is not surprised by it.
- **Handoff prompt** (ready to paste): a `pbf feat <slug>` line plus a 3 to 5 sentence
  inline brief that includes the caveat and the capability's acceptance tests (they are
  written first — the repo is test-first). Make clear the user runs this to start the
  worktree; this skill does not start it.

## Honesty rules

- Ground every shipped / pending / deferred claim in a named file. Do not assert from
  memory; the code and git history win over the docs.
- **Almost nothing has shipped yet.** Until real capability commits exist, say the state is
  "not started" rather than implying progress. The same contract the product enforces
  applies to this skill: `UNVERIFIED` is not passed off as `REPRODUCED`.
- If the strongest-looking candidate has a real blocker, say so and rank it accordingly
  rather than papering over it.
- Recommend only capabilities the files support. If the files are thin, say the pick is
  based on discussion, not an artifact.

## Common mistakes

| Mistake | Fix |
|---|---|
| Inventing a capability not in the docs | The candidate set is C1..C8 in `CAPABILITY_ROADMAP.md`; cite where each came from |
| Recommending a capability whose dependencies are unbuilt | Check the dependency line; the pick must be unblocked |
| Re-recommending shipped work | Check `git log` and the test suite first, not the prose |
| Re-recommending blocker-deferred work | Read the `docs/planning` deferral note; name the blocker |
| Recommending a bare LLM judge / an AI "reviewer" | Drop it against the `CLAUDE.md` guardrails — execution decides the verdict |
| Reaching for C8 (hosted layer) early | It's the business, and it depends on C4+C5+C6; the deterministic spine ships first |
| Building past an uncleared phase gate | Before the Phase 0 gate, the work is whatever earns the number |
| Under-weighting C4 | It's the critical path and the moat (R1/R2); C5/C6/C8 all block on it |
| Starting the worktree from this skill | Only recommend and hand off; the user runs `pbf` |
| A vague pick with no slice | Prefer a candidate with a clear, testable first slice |
