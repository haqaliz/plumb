# C1 claim recovery on the gate paper — issue card

Source: inline brief from the `plumb-next` handoff (no GitHub issue — slug id). Capability:
`docs/technical/CAPABILITY_ROADMAP.md` C1 (follow-on slice); origin: the gate-paper PRD's
nice-to-have "C1 follow-on card drafted from M3's causes" (`docs/planning/gate-paper/prd.md`);
evidence: `fixtures/gate/agrodesign/README.md` ("C1 on this paper", "Known limits").

## Brief

C1 follow-on: raise automatic claim recovery on the AgroDesign gate paper
(`fixtures/gate/agrodesign/`) from 0/86, using the 86 curated, verbatim-grounded claims in
`claims.json` as labels. Causes (fixture README / gate-paper PRD): §4 "Experimental Validation"
is not recognised as a results section (241 `outside_sections`); PDF tables arrive as
whitespace-delimited rows, not Markdown tables; glued `value<bound` tokens (e.g.
`145.333<0.001`) need splitting. Fix all three deterministically and generally — no LLM, no
per-paper special-casing.

Acceptance tests, written failing first:
1. Recall on the 86 AgroDesign claims (matched by `Claim.id`) meets a floor set in the PRD,
   and every miss carries a named cause.
2. No regression: the five `fixtures/papers/` recovery floors, the 73-row blind selection set
   (1.0/1.0), and PDF↔Markdown claim-id equality.
3. The "p ¡ 0.001" pair stays unrepresentable unless a grounded repair is tested.

Caveat (R3): the curated rule takes every numeric table cell, and some (df, N) may rightly fail
selection — set the floor honestly rather than chasing 86/86. Update the 0/86 line in the
fixture README, `CLAUDE.md` and `CAPABILITY_ROADMAP.md` with the new number.
