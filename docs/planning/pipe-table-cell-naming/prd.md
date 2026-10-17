# PRD — pipe-table-cell-naming (C1 follow-on)

Unit: `feat pipe-table-cell-naming` · Owner: aliz · Capability: **C1 — paper-claim extraction**
(`docs/technical/CAPABILITY_ROADMAP.md`) · Source brief: `docs/planning/_card/issue.md` ·
Understanding: `docs/planning/pipe-table-cell-naming/understanding.md`.

## Problem Statement

**For whom:** anyone extracting claims from a paper whose results live in ordinary Markdown pipe
tables — the majority of papers — and, downstream, **C7** (internal-consistency checks), which
depends on table cells being metric-named.

An ordinary GFM pipe-table cell is parsed as a cell with **no name** (`tables.py:241-294`;
`Table` is `cells + span`, no caption). In `candidates.py` every pipe cell is paired with
`cell_header=None` (`candidates.py:546-561`), and `select` derives a metric only from the cell's
own text (`metric_of`, `selection.py:405-449`) — which a bare numeric cell like `0.87` cannot
supply. So the cell is refused **`no_named_metric`** (`selection.py:541-542`). The caption-led
**whitespace** path, by contrast, names each cell `Table {N} {row_label} {column_header}`
(`tables.py:434-447`).

**Evidence it is real:** every Table 2 `M (SD)` cell in `fixtures/papers/PMC12780771.md:146-149`
is currently refused `no_named_metric`, and C7 cannot run GRIM on it. The gap was already called
out as a named follow-on (`CAPABILITY_ROADMAP.md:85`;
`docs/planning/claim-recovery/whitespace-tables/plan_20260927.md:8-14`), and the naming logic
already exists for the label files (`labelling._cell_contexts`, `labelling.py:320-350`).

**Cost of the status quo:** table-borne claims are under-extracted, shrinking the claim set C4 can
bind (coverage), and C7 is blocked.

## Goals & Success Metrics

- A pipe-table cell carries a metric name, so bare cells stop being refused for lack of one.
- **No committed fixture claim moves.** The pdf-seam floors (abstract exact 100% by id,
  whole-paper ≥0.90) and the AgroDesign recovery floors (recall/precision ≥0.95, distinct ids)
  stay green — measured by those existing tests.
- The naming logic has **one source of truth** (`candidates` and `labelling` cannot drift);
  label-file output stays byte-identical.
- The C7 target (`PMC12780771` Table 2) becomes metric-named.

## Requirements

### Must-have

1. **A shared pipe-cell naming helper** extracted from `labelling._cell_contexts`
   (`labelling.py:320-350`): given a table's cells, derive `{column: header_text}` from row 0 and
   `{row: label_text}` from column 0, and produce a name per cell. Both `candidates.py` and
   `labelling.py` consume it; label output is unchanged.
2. **Name format:** `Table {index} {row_label} {column_header}` when a `Table N` caption line is
   found near the table (deterministic "near" rule: the nearest preceding line matching a
   `Table N` caption, within a bounded distance), else `{row_label} {column_header}`. Degrade
   gracefully when the row label or column header is empty (use the non-empty part; never emit a
   name for a cell with neither).
3. **Pipe cells get `cell_header`** in `candidates.py` (the sole setter, `:612`): replace
   `(cell, None)` at `:549-551` with the computed name; update the docstring (`:294-297`).
4. **Header is a fallback to the in-cell metric.** In `select` (`selection.py:537-542`), compute
   `metric = metric_of(...)` first; only if it is `None`, use `_header_metric(cell_header)`. This
   preserves every existing claim id (an in-cell metric wins) and adds a metric only to
   previously-refused cells. `_header_metric` treats an empty header as `None` so it yields the
   selection cause `no_named_metric`, not the gate cause `unnamed_metric`.
5. **No fixture claim moves** — verified by `tests/extract/test_pdf_seam.py` and
   `tests/gate/test_agrodesign_recovery.py` staying green with unchanged floors.
6. **Determinism** preserved (canonical serialization byte-identical across processes).

### Should-have

7. A regression test asserting the `PMC12780771` Table 2 `3.72 (0.57)` cell is metric-named
   (admitted, or at least no longer `no_named_metric`).

### Nice-to-have

8. Multi-row headers (a header that is itself a data row, as in `PMC12780771.md:131`) — out of
   scope for this slice; name by row label + row-0 header only.

## Technical Considerations

- **Layering:** naming is a parsing concern (`tables`/`candidates`), metric *choice* is selection
  (`selection`). The helper lives with the table parsers; `select` only decides precedence.
- **Precedence is the safety mechanism.** The global fallback (decided) is what guarantees the
  acceptance "no fixture claim moves"; if the seam/AgroDesign tests show a captioned cell with an
  in-cell metric shifting, narrow the fallback to pipe-sourced cells (a `Candidate` flag).
- **The "Table N near" rule must be deterministic and offline** — no fuzzy matching; a bounded
  line window preceding the table block.
- **N-token guard:** row labels/headers that are sample sizes (`n = 1578`, `n`, `N`) must stay
  refused (`_N_TOKENS` `selection.py:178-191`); a combined `{row} {col}` name could end in a
  non-N token while still naming a sample size — verify `_header_metric` still refuses the
  sample-size-metric cells.
- **No new dependency, no network.** Offline, deterministic tests.

## Risks & Open Questions

- **Global fallback touching a captioned cell.** If any captioned whitespace cell carries an
  in-cell metric today, its metric changes. *Mitigation:* the seam + AgroDesign tests; narrow the
  fallback if they move.
- **Multi-row headers** mean the C7 target is named by row label only (`Date orientation`), not
  `Mean (SD)`. Documented limit; acceptable for this slice.
- **Path asymmetry in the seam:** the CSV/PDF converter emits GFM pipe rows, so both the Markdown
  and PDF paths name the same cells; a newly id-matched prose occurrence could enter the seam bar
  (`test_pdf_seam.py:177-183`). The floors test guards it.
- **Open question:** does the `Table N` caption lookup use the line immediately preceding the
  table, or a bounded window? Settle in the plan; prefer the nearest preceding caption line within
  a small window, deterministic.

## Out of Scope

- C7 GRIM/statcheck itself (a separate unit; this only unblocks it).
- Scale/item-count metadata carriage (C7's other need; a separate follow-on).
- Multi-row header semantics beyond row-0 header + column-0 label.
- Any change to the whitespace-table name format, the PDF converter, or the label-file content.
- LLM assistance; anything network.

## Acceptance Criteria (written first — the repo is test-first)

1. `test_candidates.py`: a pipe cell in a near-captioned table has
   `cell_header == "Table {n} {row_label} {column_header}"`; an uncaptioned pipe cell has
   `"{row_label} {column_header}"`; the existing `test_a_pipe_table_cell_has_no_header`
   (`:758-762`) is inverted (RED first).
2. `test_selection.py`: a pipe cell whose text already yields an in-cell metric keeps that metric
   (id unchanged); a bare numeric pipe cell (`metric_of` None) now takes the header metric and is
   admitted.
3. Shared helper: `candidates` and `labelling` call one function; `tests/extract/test_labelling.py`
   stays green byte-identical.
4. `test_pdf_seam.py` and `test_agrodesign_recovery.py` stay green with unchanged floors (no
   committed fixture claim moves).
5. The `PMC12780771` Table 2 cell `3.72 (0.57)` is metric-named (regression test).
6. Determinism tests stay green (byte-identical across processes); `uv run pytest -q` green; no
   network.
