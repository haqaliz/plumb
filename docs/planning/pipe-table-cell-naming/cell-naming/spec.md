# Spec — cell-naming (pipe-table-cell-naming)

Source: `docs/planning/pipe-table-cell-naming/prd.md` (approved 2026-10-17). One aspect: name
ordinary Markdown pipe-table cells (reusing the logic the label path already has), without moving
any committed fixture claim.

## Problem slice

An ordinary GFM pipe-table cell is parsed with no name (`tables.py:241-294`; `Table` = cells +
span). `candidates.py` pairs every pipe cell with `cell_header=None` (`:546-561`), so `select`
can only derive a metric from the cell's own text (`metric_of`), and a bare numeric cell is
refused `no_named_metric` (`selection.py:541-542`). Name pipe cells like the whitespace path does,
so bare cells gain a metric, and make the header a **fallback** so existing claims do not move.

## In scope

- A shared pipe-cell naming helper (extracted from `labelling._cell_contexts`).
- `candidates.py`: set `cell_header` for pipe cells.
- `selection.py`: header becomes a fallback to the in-cell metric; `_header_metric` treats an
  empty header as `None`.
- Tests: pipe naming, precedence, the C7 target cell, and the unchanged-floor guards.

## Out of scope

- C7 GRIM; scale/item-count metadata; multi-row header semantics; whitespace format; the PDF
  converter; label-file content.

## Acceptance criteria (testable; written first)

1. `test_tables`/`test_candidates`: a pipe cell in a near-captioned table has
   `cell_header == "Table {n} {row_label} {column_header}"`; an uncaptioned pipe cell has
   `"{row_label} {column_header}"`; neither label nor header ⇒ no name (`None`).
2. `test_selection`: a pipe cell whose text yields an in-cell metric keeps it (id unchanged); a
   bare numeric pipe cell takes the header metric and is admitted; a sample-size column
   (`n`/`N`/`n = 5`) still yields no metric.
3. `labelling` uses the same helper; `test_labelling` stays green byte-identical.
4. `test_pdf_seam` (abstract exact 100% by id; whole-paper ≥ 0.90) and
   `test_agrodesign_recovery` (recall/precision ≥ 0.95; distinct ids) stay green.
5. A regression test asserts the `PMC12780771` Table 2 cell `3.72 (0.57)` is metric-named.
6. `uv run pytest -q` green; no network; canonical serialization byte-identical across processes.

## Dependencies & sequencing

Independent; ships as one aspect. Only `src/plumb/extract/` and `tests/extract/` change.

## Open questions / risks

- If the AgroDesign recovery precision drops (new pipe-cell claims are wrong), narrow the naming
  (e.g. require a non-empty, non-sample-size column header) rather than weaken the floor.
- The caption "near" rule must be deterministic (nearest preceding `Table N` line within a small
  fixed window).
