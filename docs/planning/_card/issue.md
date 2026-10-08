# Brief — notebook-capture (C3, named follow-on)

Source: `pbf feat notebook-capture` handoff from `plumb-next` (2026-10-08). No GitHub issue
exists for this work (`gh issue list` is empty); the id lives in the branch and PR.

## Brief

Build C3's named follow-on test-first: **notebook entry-point resolution and cell-output
capture**, so a repo whose only entry is an executed `analysis.ipynb` can run and have each
cell's outputs content-addressed into the per-run object store. This is the repo's own
first-listed engine gap blocking panel growth: *"Growing the corpus is blocked by named
engine gaps, in order: notebook-cell capture (C3), a poetry env policy (C2), and
figure-with-data locators"* (`docs/planning/cross-paper-coverage/panel-run/screening.md:296-298`;
`docs/technical/CAPABILITY_ROADMAP.md:236-241`). R1 is High/High and "notebook cell" is its
named mitigation (`docs/ROADMAP.md:90`). Notebook-rendered results are the dominant failure
mode across both selection passes (`docs/planning/gate-paper/survey.md:47-48`;
`screening.md:46,61,293-294`).

The named follow-on in the design docs: `docs/planning/execution-capture/prd.md:108`
("Notebook cell capture (follow-on, needs nbconvert)") and
`docs/technical/ARCHITECTURE.md:109` ("Notebook cell capture is a named follow-on").

**Coupled follow-on, not this unit's scope unless it falls out naturally:** C4's
notebook-cell locator (`docs/planning/binding-verdict/prd.md:238`) — capture alone yields no
verdicts.

**Caveat:** nbconvert is a transitive dependency in a repo that deliberately holds exactly
one runtime dep today (pypdf). Keep execution behind a runner seam like C2's:
`build_environment`'s runner pattern — tests stay offline with synthetic `.ipynb` fixtures
and a stub runner; the real kernel runs only at dev time, and whatever nbconvert pulls in is
pinned and recorded as C2 records its tools. Unseeded notebooks will still end `UNVERIFIED` —
capture unlocks the class, it does not guarantee verdicts (R1 stays honest).

**Acceptance tests, written first:**
1. A synthetic executed `.ipynb` in a run's working copy yields per-cell captured outputs,
   readable only by hash through `Capture.read` (content-addressed, like JSON/CSV outputs).
2. A committed (stale) notebook is `STALE_ARTIFACT` — its bytes are never read (constraint
   #5, reproduce what ran).
3. Notebook entry-point resolution: zero or many notebook candidates are
   `ENTRYPOINT_MISSING`/`ENTRYPOINT_AMBIGUOUS`, never a guess.
4. The `RunTrace` stays byte-identical across processes, with no absolute paths and no
   clock.
5. The full suite stays green and network-free under the autouse blocker
   (`tests/conftest.py:56-60`); real kernel execution runs only at dev time, never in
   tests or CI.
