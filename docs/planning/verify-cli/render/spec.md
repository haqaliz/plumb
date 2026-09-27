# render — aspect spec

Problem slice: the machine contract (`--json`) and the human contract (fixed-layout table) for
the verdict table, both byte-identical across invocations. This is what "returns a per-claim
verdict table" (`docs/ROADMAP.md:38`) concretely means, and the determinism guarantee is the
engine's canonical-JSON family extended to the CLI surface.

## In-scope requirements

- `--json`: canonical JSON on stdout — the engine's convention
  (`sort_keys=True, ensure_ascii=False, separators=(",",":"), allow_nan=False, utf-8, one
  trailing newline`, `src/plumb/extract/serialize.py:81-129`). Schema: a single object with
  `run_id`, `coverage` (from `VerdictSet.coverage`, `src/plumb/verify/verdict.py:128-140`),
  and `verdicts` (array of per-claim records carrying the same fields as
  `serialize_verdicts`, `src/plumb/verify/serialize.py:40-47` — claim_id, verdict, cause,
  reported_text, artifact, locator, located_text, sha256, run_id, rederived, band,
  tolerance_band, threshold, tolerance_threshold, delta, review_required).
- Human table (no `--json`): fixed-layout, monospace-friendly, one row per claim sorted by
  claim_id: columns `VERDICT`, `CAUSE`, `CLAIM ID`, `REPORTED`, `REDERIVED`, `ARTIFACT`,
  `LOCATOR`; then a summary block: totals per verdict kind + `bound`/`claims` from coverage.
  No timestamps, no cwd, no env, no padding derived from volatile data.
- Byte-identical: two invocations on the same input (same process and cross-process with
  varied PYTHONHASHSEED) produce identical stdout for both `--json` and the table. Verified
  by tests in the `tests/extract/test_determinism.py` style (subprocess spawns).
- Empty and degenerate sets render sensibly: zero claims (empty verdicts array / "0 claims"
  table + summary), all-`UNVERIFIED` run (full table, summary, exit 1 — exit code owned by
  the caller, not the renderer).
- Verdict kind ordering in the summary is fixed (REPRODUCED, WITHIN-TOLERANCE, DIVERGED,
  UNVERIFIED); causes sorted alphabetically in `by_cause`.

## Out-of-scope boundaries

- No exit-code logic in the renderer (caller decides; renderer returns bytes).
- No table pagination, no colors, no terminal width detection, no CSV/TSV output.
- No rendering of bundle members (that's `verify_bundle`'s report, untouched).

## Acceptance criteria (testable, written failing first)

1. `--json` output for the replayed AgroDesign record is byte-identical to a golden file
   derived from the committed `verdicts.json` (same fields; the schema's `coverage` matches
   `VerdictSet.coverage` recomputed from the committed record) — cross-process subprocess test.
2. Human table output for the same record matches a golden fixture byte-for-byte (fixed
   widths, fixed order, fixed summary).
3. Two subprocess invocations under different `PYTHONHASHSEED` produce identical bytes for
   both formats.
4. Zero-claim and all-`UNVERIFIED` verdict sets render without error and with the documented
   shape (tests construct `VerdictSet` directly, using existing helpers).
5. `--json` output parses with `json.loads`, validates against the schema's field set, and
   contains no `NaN`/`Infinity` (allow_nan=False would raise — the test asserts the raw bytes).

## Dependencies and sequencing

Depends on cli-core's dispatcher contract (the renderer is called with a `VerdictSet` and
returns bytes; the shell writes them). No dependency on replay/live-spine internals — tests
feed `VerdictSet`s built from the committed record via the existing replay helpers
(`tests/gate/test_agrodesign_replay.py:34-47`).

## Open questions / risks

- Golden-file strategy: committing golden output files vs asserting against derived
  expectations. Repo precedent is byte-equality against committed serialized records
  (`test_agrodesign_replay.py` asserts `serialize_verdicts(...) == verdicts.json`) — prefer
  committed goldens for the table (its exact layout is otherwise unpinned) and derived
  expectations for `--json` (its field set is already pinned by `serialize_verdicts`).
- Long `REPORTED`/`REDERIVED` text: truncation policy must be fixed (e.g. 24 chars + `…`) or
  the table can't be fixed-width. Decide: fixed truncation at 24 chars, documented.