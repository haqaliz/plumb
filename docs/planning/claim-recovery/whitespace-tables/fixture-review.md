# Fixture review — `whitespace-tables`

Measured on the branch after "Name captioned-table cells by table, row and column", against
the state after `sections-precision` (`../sections-precision/baseline.md`).

## Where the recogniser fires

| Paper | Markdown path | PDF path |
|---|---|---|
| PMC12780771 | 0 | 0 |
| PMC13134363 | 0 | 0 |
| PMC13298092 | 0 | 0 |
| PMC13332965 | 0 | 0 |
| PMC13363872 | 0 | 0 |
| AgroDesign | — | 7 tables (Tables 1–7), 71 cells |

The fixture PDFs' captions wrap over several lines and are followed by caption text, pipe
fragments or headers that do not fit a row, so the strict shape (a single caption line,
an optional header that fits the first row, then ≥ 2 rows) never matches. **No fixture
claim changed on either path** (0 added, 0 dropped, 0 renamed); the seam test's inputs are
unchanged. Gap 1 of the PRD self-critique did not materialise.

## AgroDesign

| | sections-precision | whitespace-tables |
|---|---|---|
| Claims emitted | 86 | 86 |
| Curated recovered (place + value) | 86 / 86 | 86 / 86 |
| Distinct ids | 79 | **86** |

Table 8 (4 cells) is not recognised: its header row arrives as the heading
`## Genotype BLUP`, and a heading is not a header (spec). Its cells still recover, named
from the prose path (`G`), with distinct ids because their values differ. Reading a
heading as a header when it fits the first row is a possible follow-on, not done here.
