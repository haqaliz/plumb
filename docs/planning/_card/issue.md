# Brief — notebook-cell-locator (C4, follow-on)

Source: `pbf feat notebook-cell-locator` handoff from `plumb-next` (2026-10-10). No GitHub
issue exists for this work (`gh issue list` is empty); the id lives in the branch and PR.

## Brief

Build C4's **`notebook_cell` locator** test-first, so a claim can bind to a captured cell
artifact (`<relpath>#cell-<i>`, the canonical `outputs` JSON) and be compared — the named
immediately-next unit after notebook capture shipped (`docs/planning/notebook-capture/prd.md:23`);
without it, notebook capture yields **no verdicts** and R1's number does not move
(`docs/planning/notebook-capture/understanding.md:18-19`, `notebook-capture/spine/spec.md:23`).

The repo's own named engine gaps: *"Growing the corpus is blocked by named engine gaps, in
order: notebook-cell capture (C3), a poetry env policy (C2), and figure-with-data locators"*
(`docs/planning/cross-paper-coverage/panel-run/screening.md:296-298`;
`docs/technical/CAPABILITY_ROADMAP.md:236-241`). Notebook-cell capture (C3) landed 2026-10-08
(`0d60c59`); this unit is the other half of the first gap. R1 is High/High and "notebook cell"
locators are its named mitigation (`docs/ROADMAP.md:90`). Notebook-rendered results are the
dominant failure mode across both selection passes (`docs/planning/gate-paper/survey.md:47-48`;
`screening.md:46,61,293-294`).

**Caveat (R2):** a wrong cell binding could fabricate a `DIVERGED`; the new locator must sit
under run-cause precedence and the mutation-checked false-`DIVERGED` guard
(`tests/verify/test_false_diverged_guard.py`), with `review_required`. The canonical cell
`outputs` list is multi-output, so the locator grammar (which output, which field) is a PRD
decision. There is **no real notebook paper fixture** yet — only the stub-kernel dev probe
(`tools/notebook_probe.py`, `docs/planning/notebook-capture/spine/probe_20261008.md`); a real
notebook fixture is dev-time work like Perrin's (`fixtures/gate/perrin/`).

**Acceptance tests, written first:**
1. A `notebook_cell` binding locates a value inside the cell's canonical `outputs` JSON, read
   only through `Capture.read` (hash re-checked); zero/many target outputs →
   `NO_BINDING`/`AMBIGUOUS_BINDING`, never a guess.
2. A committed (stale) cell is `STALE_ARTIFACT` — its bytes are never read (constraint #5,
   reproduce what ran).
3. No harness-side failure becomes `DIVERGED` on the new path — the false-`DIVERGED` guard is
   extended and mutation-checked over the new locator; every `DIVERGED` carries
   `review_required`.
4. Record → `--from-record` replay stays byte-identical with a `notebook_cell` binding, and
   `build_bundle`/`verify_bundle` round-trip the new locator (only outputs the run produced).
5. The full suite stays green and network-free under the autouse blocker
   (`tests/conftest.py`); real kernel execution runs only at dev time, never in tests or CI.