# feat pipe-table-cell-naming — C1 follow-on

Source: `plumb-next` pick 2026-10-17, pivoted after the C7 dig (no GitHub issue; slug id).

## Brief

Name ordinary Markdown **pipe-table** cells by table, row and column, the way the caption-led
whitespace-table path already does, so a table cell can be grounded as a metric-named claim (or
carry the name for a later C7 check). Today `Candidate.cell_header` is populated **only for
caption-led whitespace tables** (`src/plumb/extract/candidates.py:294-296`); ordinary pipe-table
cells fall back to `metric_of` reading the preceding clause
(`src/plumb/extract/selection.py:400-424`), so most table cells are refused `no_named_metric`.
This is the already-named C1 follow-on ("Pipe-table cells stay unnamed — a named follow-on",
`docs/technical/CAPABILITY_ROADMAP.md:85`) and it unblocks C7's GRIM slice on real fixtures
(e.g. `fixtures/papers/PMC12780771.md` Table 2 `M (SD)` cells) while improving claim coverage
generally.

Candidate acceptance tests (written first, offline, deterministic):
1. A pipe-table cell in a captioned Markdown table is named `<table> <row> <column>` (or the
   paper's own row/column labels) into `Candidate.cell_header`, matching the whitespace-table
   naming convention.
2. A previously `no_named_metric` Table-2 cell (e.g. PMC12780771 Date-orientation `3.72 (0.57)`)
   becomes an admitted claim (or is at least metric-named) after the change, at the recovery
   floor.
3. Existing whitespace-table naming and all five PDF/Markdown fixtures are unchanged (no fixture
   claim moves) — the pdf-seam recovery floors hold.
4. Byte-identical serialization / determinism preserved; `uv run pytest -q` green; no network.

## Grounding

- `docs/technical/CAPABILITY_ROADMAP.md:85` (the named follow-on) and the claim-recovery slice.
- `src/plumb/extract/candidates.py:294-296`, `src/plumb/extract/selection.py:400-424,458-468`,
  and the whitespace-table naming in `src/plumb/extract/tables.py`.
- Unblocks C7: `docs/technical/CAPABILITY_ROADMAP.md:315-321`; the C7 dig (2026-10-17) found
  `PMC12780771` Table 2 means are the only GRIM-suitable data and they are currently refused.
