# Claim-count baseline — `sections-precision`

Claims emitted by `extract_claims` on `master` (`2bc53fa`), per paper and path. The after
column is filled in by Phase 5. Measured by a scratch script: for each `fixtures/papers/PMC*.md`,
`extract_claims(md)` and `extract_claims(pdf_to_markdown(pdf))`; AgroDesign through the PDF.

| Paper | Path | Before | After |
|---|---|---|---|
| PMC12780771 | md | 27 | 27 |
| PMC12780771 | pdf | 263 | 263 |
| PMC13134363 | md | 78 | 78 |
| PMC13134363 | pdf | 242 | 242 |
| PMC13298092 | md | 56 | 55 |
| PMC13298092 | pdf | 179 | 178 |
| PMC13332965 | md | 56 | 56 |
| PMC13332965 | pdf | 93 | 93 |
| PMC13363872 | md | 67 | 67 |
| PMC13363872 | pdf | 84 | 84 |
| AgroDesign | pdf | 0 | 86 |

The PDF path emits far more claims than the Markdown path on every fixture. That predates
this work: the seam test (`tests/extract/test_pdf_seam.py`) measures recovery of the Markdown
path's abstract and non-table claims, not equality of the two sets.

## After (`cd11645`) — every changed claim, reviewed

| Paper | Path | Change | Claim | Cause | Review |
|---|---|---|---|---|---|
| PMC13298092 | md | dropped | `3` (metric `##`) | `layout_numeral` | The enumerator of `## 3. Results`; not a value — correct |
| PMC13298092 | pdf | dropped | `3` (metric `#`) | `layout_numeral` | Same heading on the PDF path — correct |

No other fixture claim changed, on either path. No genuine claim was dropped.

AgroDesign: 86 emitted, 86/86 curated recovered (place + value), precision 86/86; the two
`p ¡ 0.001` are refused `partial_value`. **Open for `whitespace-tables`:** 86 claims carry
only 79 distinct ids — distinct table cells share `(text, metric, units)`.
