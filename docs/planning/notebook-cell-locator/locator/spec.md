# Spec — notebook-cell-locator / locator

One aspect: the whole unit, planned in `plan_20261010.md`. The PRD is the contract
(`docs/planning/notebook-cell-locator/prd.md`); decisions D1–D7 are pinned there.

## Problem slice

A claim may bind to a captured cell artifact (`<relpath>#cell-<i>`, the canonical `outputs`
array — `src/plumb/run/capture.py:136-187`) and decide a verdict, with the same honesty
contract as the three existing locators: read only through `Capture.read`, stale bytes never
read, no harness-side failure becomes `DIVERGED`.

## In scope

- `bindings.py`: `NotebookCell` kind, fields exactly `{kind, pointer}`, RFC 6901 pointer
  (D1), `.ipynb#cell-<n>$` artifact gate (D1), per-entry `invalid` semantics preserved.
- `locate.py`: dispatch + `_notebook_cell` reader; pointer over the parsed canonical array;
  leaf rules (D2/D7); `_stale_target` resolves cell → notebook file (D3); `float_repr`
  honored on the shared parse path (D4); no float reaches a comparison (D7).
- `serialize.py`/`cli/render.py`: canonical locator JSON and table rendering (D6).
- False-`DIVERGED` guard: notebook-cell scenarios + mutation coverage (R2).
- Round-trips: record/replay/bank/bundle with a `notebook_cell` binding, byte-identical.
- Dev-time probe (`tools/notebook_locator_probe.py`) + evidence doc.

## Out of scope

Real notebook paper fixture (successor unit); poetry policy (C2); figure locators; binding
proposer; new causes; `AMBIGUOUS_BINDING` emitter (unreachable, D2); whole-file `notebook`
artifacts as bind targets; `execution_count` addressing.

## Acceptance criteria (testable)

1. A `notebook_cell` binding locates a value inside the cell's canonical `outputs` array via
   `Capture.read` (hash re-check); unresolved pointer / absent artifact → `NO_BINDING`; a
   list/object node leaf → `UNPARSEABLE_VALUE`; never a guess (D2).
2. A stale notebook file makes its cells `STALE_ARTIFACT`, bytes never read (D3).
3. The false-`DIVERGED` guard is extended; mutations of the guard fail the suite; every
   `DIVERGED` carries `review_required` (unchanged semantics, verdict.py:107-109).
4. `verdicts.json` carries the canonical locator JSON, byte-identical across processes;
   record → `--from-record` replay, `--bank`, `build_bundle`/`verify_bundle` round-trip the
   new binding identically.
5. No new cause in any vocabulary (`test_cause_catalogue` still asserts emitted == `CAUSES`);
   suite green and network-free; kernels only at dev time.

## Dependencies / sequencing

Depends on C3 notebook capture (shipped, `0d60c59`) and the C4 first slice. Phases are
sequential: schema → locate → staleness/guard → serialize/render → round-trips → probe.

## Open questions / risks

- R2 stale-leak via cell names (mitigated D3 + mutation-checked guard); the number-leaf
  transport decision is D7; catalogue row optional (PRD should-have #10).