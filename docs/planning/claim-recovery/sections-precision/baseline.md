# Claim-count baseline — `sections-precision`

Claims emitted by `extract_claims` on `master` (`2bc53fa`), per paper and path. The after
column is filled in by Phase 5. Measured by a scratch script: for each `fixtures/papers/PMC*.md`,
`extract_claims(md)` and `extract_claims(pdf_to_markdown(pdf))`; AgroDesign through the PDF.

| Paper | Path | Before | After |
|---|---|---|---|
| PMC12780771 | md | 27 | |
| PMC12780771 | pdf | 263 | |
| PMC13134363 | md | 78 | |
| PMC13134363 | pdf | 242 | |
| PMC13298092 | md | 56 | |
| PMC13298092 | pdf | 179 | |
| PMC13332965 | md | 56 | |
| PMC13332965 | pdf | 93 | |
| PMC13363872 | md | 67 | |
| PMC13363872 | pdf | 84 | |
| AgroDesign | pdf | 0 | |

The PDF path emits far more claims than the Markdown path on every fixture. That predates
this work: the seam test (`tests/extract/test_pdf_seam.py`) measures recovery of the Markdown
path's abstract and non-table claims, not equality of the two sets.
