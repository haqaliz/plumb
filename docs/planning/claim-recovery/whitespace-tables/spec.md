# Aspect spec — `whitespace-tables`

Parent: `docs/planning/claim-recovery/prd.md` (M6, M7, M8). Depends on
`sections-precision`.

## Problem slice

PDF tables reach C1 as whitespace rows under a `Table N:` caption, so their cells are read
as prose and named by row label alone: distinct cells share a `Claim.id`. Recognise these
tables in `extract/tables.py` so each cell is a table cell with a unique, readable metric.

## In scope

- A caption-led whitespace-table recogniser beside the GFM pipe-table parser: caption line
  `^Table \d+[:.]`, then ≥ 2 consecutive rows, each a text label followed by ≥ 1
  numeric/dash cells; glued `value<bound` (and `value>bound`) split into two cells; the
  table ends at the first line that is not a row. An optional header row (all non-numeric
  tokens, directly after the caption) supplies column names.
- Candidates inside such a table carry `section_hint = table` and cell coordinates.
- Table-cell metric: `Table {N} {row label} {column}` where column is the header text if
  present, else `column {k}`.
- Floors: precision/recall on all 86; zero id collisions across distinct cells; fixture
  README, `CLAUDE.md`, `CAPABILITY_ROADMAP.md` updated; the 0/86 pin replaced.

## Out of scope

- Converter changes; header inference across tables; multi-line row labels.

## Acceptance criteria (tests written first)

1. Synthetic: a caption + 3 rows parse into a table with the right cells; `145.333<0.001`
   yields two cells; `– –` cells yield no candidates.
2. Synthetic: a caption followed by one prose line is **not** a table; a pipe table is never
   re-read as a whitespace table.
3. Header present → `Table 1 Treatment MS`; absent → `Table 3 Nitrogen column 3`.
4. AgroDesign: no two emitted claims at distinct locations share an id.
5. AgroDesign: recall ≥ 0.95 and precision ≥ 0.95 on all 86 (D2); misses listed with causes.
6. No regression: blind score, the five fixture floors, the PDF↔Markdown seam (a fixture
   whose output changes must still meet its floor), the bundle verification test.
