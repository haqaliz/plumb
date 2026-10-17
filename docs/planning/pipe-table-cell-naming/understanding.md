# Understanding — pipe-table-cell-naming (C1 follow-on)

Source: `docs/planning/_card/issue.md` (plumb-next pick, pivoted after the C7 dig, 2026-10-17).
One dig agent mapped the table-naming path on 2026-10-17.

## What the work is really asking

Give an **ordinary Markdown pipe-table cell** the same kind of name the caption-led
**whitespace-table** path already gives its cells, so a table cell can carry a metric instead of
being refused. This is the already-named C1 follow-on (`CAPABILITY_ROADMAP.md:85`;
`docs/planning/claim-recovery/whitespace-tables/plan_20260927.md:8-14`). It unblocks C7's GRIM
slice (the only GRIM-suitable fixture, `PMC12780771` Table 2, is currently un-extracted) and
improves claim coverage for every table paper.

## The gap, grounded in code

- **Two parsers, one naming path.** `parse_tables` handles GFM pipe tables and yields **cells
  only, no names** (`src/plumb/extract/tables.py:241-294`); the `Table` record is
  `cells + span` — **no caption/number** (`tables.py:117-147`). `parse_captioned_tables` handles
  caption-led whitespace tables and builds a name
  `f"Table {number} {label} {name}"` (`tables.py:434-447`), where `number` is the caption's
  `Table N`, `label` is the row label, and `name` is the column header (or `column {k}`).
- **Only whitespace cells get a header.** In `candidates.py` the cell/header stream pairs every
  `parse_tables` cell with `None` and every captioned cell with its `.header`
  (`candidates.py:546-561`); `cell_header=header` is set at the sole site `candidates.py:612`
  (`Candidate.cell_header` docstring at `candidates.py:294-297` says "None everywhere else,
  pipe-table cells included").
- **Metric selection prefers the header.** `select` takes `_header_metric(cell_header)` when
  present, else `metric_of(...)` (`selection.py:537-542`); `_header_metric` returns the header
  unless it names a sample size (`selection.py:455-464`). A bare pipe cell has no in-cell metric
  and no header, so it hits the **selection** cause `no_named_metric` (`selection.py:77,541-542`)
  — distinct from the gate cause `unnamed_metric`, which fires only on an **empty-string** metric
  (`admit.py:94,424-425`).
- **The naming logic already exists for labels.** `labelling._cell_contexts`
  (`src/plumb/extract/labelling.py:320-350`) already derives pipe-cell
  `headers = {column: text | row==0}` and `labels = {row: text | column==0}` for the label files.
  **Reuse/share this, do not reinvent it.** The claim-selection plan anticipated exactly this
  (`docs/planning/claim-selection/selection-rule/plan_20260921.md:84-86`).

## Affected areas

- `src/plumb/extract/tables.py` — a pipe-cell naming helper (reuse `labelling`'s derivation).
- `src/plumb/extract/candidates.py` — set `cell_header` for `parse_tables` cells
  (`:546-561`), update the docstring (`:294-297`).
- `src/plumb/extract/selection.py` — decide `cell_header` vs in-cell `metric_of` precedence
  (`:537-542`); `_header_metric` empty-header handling (`:455-464`).
- `tests/extract/` — `test_tables.py` (pipe naming), `test_candidates.py`
  (`test_a_pipe_table_cell_has_no_header` at `:758-762` must be inverted, test-first),
  `test_selection.py` (`TestCellHeaders` `:351-371`).
- Fixtures/tests that must not move: `tests/extract/test_pdf_seam.py` (floors: abstract exact
  100% by id, whole-paper ≥0.90; `FLOOR=0.90` `:62`), `tests/gate/test_agrodesign_recovery.py`
  (recall/precision ≥0.95; distinct-id `:90-102`), and the signed bundle / `tools/bundle_replay.py`.

## Tensions / risks to flag (do not paper over)

1. **`Claim.id` churn.** `Claim.id` hashes `(value_text, metric, units)` (`claim.py:61-70`), and
   `select` **always prefers `cell_header` over `metric_of`** (`selection.py:537-540`). A pipe cell
   that already carries its own notation (`p < 0.001` → metric `p`, `95% CI: ...`,
   `0.85 ± 0.03`) would, once named, get the header instead — changing its id and moving the
   pdf-seam recovery, the AgroDesign distinct-id floor, determinism snapshots, and the bundle.
   Mitigation to decide: make the header a **fallback** (`metric_of` first, then header) so
   existing ids are preserved and only currently-refused cells gain a metric.
2. **No table number for pipe tables.** The whitespace name embeds `Table {number}` from a
   caption; pipe tables have no caption/number field. The pipe name must either hunt a preceding
   `Table N` line or use a caption-free form (row label + column header), diverging from the
   whitespace format.
3. **Multi-row headers.** `PMC12780771` Table 2's real label `Mean (SD) or %` is a **data** row,
   not row 0 (`PMC12780771.md:131`); the target `3.72 (0.57)` would be named only by its row
   label (`Date orientation`), not `M (SD)`. Row-0 numeric headers and ragged rows are further
   limits (`labelling.py:327-330`, `plan_20260927.md:122-124`).
4. **Empty / N-token headers.** `_header_metric("")` returns `""` → the gate `unnamed_metric`, not
   the selection `no_named_metric` (a different surface). Row labels/headers like `n = 1578`,
   `n`, `N` must stay refused (`_N_TOKENS` `selection.py:178-191`); a combined name that does not
   *end* in an N-token could slip past `_header_metric`, which tests only the ending.
5. **Path asymmetry in the seam.** The PDF converter emits GFM pipe rows
   (`pdf/convert.py:1078-1088`), so both paths should name identically; the seam excludes a claim
   from the bar only if **every** occurrence is inside a pipe row (`test_pdf_seam.py:177-183`) —
   a newly-id-matched prose occurrence could enter the bar and lower recovery.
6. **Labels cannot validate.** Every committed label row is abstract-only
   (`fixtures/labels/PMC*.todo.jsonl`), so no label exercises a pipe cell; validation rests on
   the seam floors and targeted fixture claims, not the label set.

## Place in the pipeline

**C1 — claim extraction** (the input to the moat). Guardrail-safe (deterministic parsing, no LLM,
no network). It improves the claim set that C4 binds, and unblocks **C7** (internal-consistency),
which the dig showed is otherwise blocked by this gap plus missing scale/item-count metadata.

## Open questions (for the requirements interview)

1. **Name format** for a pipe cell (no caption/number exists): `{row_label} {column_header}`? a
   searched `Table N {row} {col}`? the `labelling` `column_header`/`row_label` pair?
2. **Precedence** — header as a **fallback** to `metric_of` (preserve existing ids) vs the current
   header-wins override? Acceptance requires no committed fixture claim to move.
3. **Scope** — name every pipe cell, or only those a bare cell would otherwise refuse
   (`no_named_metric`)? And do we unify `candidates` and `labelling` on one shared helper?
