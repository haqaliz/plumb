# Paper fixtures

Real open-access papers, used as the **blind label set** for C1's selection rule (M15).

## Why these are here, and why they are real

The selection rule must be measured against labels it did not author. Synthetic papers
would test the rule against our own idea of what a paper looks like, which is the
circularity M15 exists to prevent, in a thinner disguise. These are real papers, with
real messiness — inconsistent rounding, numbers in reference lists, sample sizes,
version strings, confidence intervals written several ways.

## Provenance

Retrieved 2026-09-21 from **Europe PMC** (`ebi.ac.uk/europepmc`), open-access subset,
with the repository owner's explicit authorization for the network fetch. Each was
published under **CC BY**, which permits redistribution with attribution.

Converted from JATS XML to Markdown (headings preserved so section hints can be derived
structurally rather than guessed). The original XML is not retained; the `<!-- source -->`
comment at the top of each file records its PMCID, DOI and license.

The `<!-- source -->` comment is the authoritative provenance record for each file.
The table below was corrected against it on 2026-09-22: **all five previously listed
DOIs were wrong** (not just the two flagged during intake — the wobble was total).
Each DOI was re-verified against the Europe PMC REST record (`PMCID:` query) and the
PMC OA dataset metadata JSON; both agree with the `<!-- source -->` comments.

| File | DOI (verified 2026-09-22) | Title |
|---|---|---|
| `PMC12780771.md` | 10.1093/aje/kwaf001 | Improving accuracy in the estimation of probable dementia in racially and ethnically diverse groups with penalized regression and transfer learning |
| `PMC13134363.md` | 10.7759/cureus.106260 | Global Autism Spectrum Disorder Prevalence Estimates and Associated Covariates: A Systematic Review and Meta-Regression Analysis |
| `PMC13298092.md` | 10.3390/diagnostics16121820 | Diagnostic Accuracy of Auricular Morphometry in Sex Estimation: A Logistic Regression Model with ROC-Based Validation |
| `PMC13332965.md` | 10.1007/s00439-026-02852-3 | Within-sibling attenuation of polygenic risk score accuracy: investigating the effects of principal component analysis, LD score regression, and mixed model association in the UK Biobank |
| `PMC13363872.md` | 10.3390/s26134093 | Understanding the Performance of Deep Computer Vision Models: A Symbolic Regression Approach to Accuracy and Latency Prediction |

The wrong DOIs previously in this table (10.1177/08919887251355507,
10.1186/s12888-025-07354-6, 10.3390/diagnostics15182386, 10.1186/s13059-025-03797-y,
10.3390/jimaging11090318) belong to other, unrelated papers and must not be cited
against these files.

## PDF fixtures

Each paper also ships as its **real journal PDF**: `fixtures/papers/PMC<id>.pdf`,
one per paper, committed as binary (`.gitattributes` has `*.pdf binary`; verified via
`git check-attr text` reporting unset). These are the publisher PDFs — Cureus
(PMC13134363), MDPI Diagnostics (PMC13298092), MDPI Sensors (PMC13363872), Springer
Human Genetics (PMC13332965), Oxford Academic Am J Epidemiol (PMC12780771) — all CC BY.

Fetched **2026-09-22**, dev-time, one-time, read-only:

- **Canonical source URLs (per Europe PMC records):**
  `https://europepmc.org/articles/PMC<id>?pdf=render` for each of the five PMCIDs.
  On the fetch date these were Cloudflare-challenged from the dev machine (HTTP 403
  "Just a moment..." on every path, with and without a browser User-Agent), and
  `pmc.ncbi.nlm.nih.gov` served a JavaScript proof-of-work gate on its `/pdf/` route —
  so the bytes were taken from the **PMC Open Access cloud dataset** (`s3://
  pmc-oa-opendata`, https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/), the same OA corpus
  Europe PMC serves, as plain HTTPS objects:
  `https://pmc-oa-opendata.s3.amazonaws.com/PMC<id>.1/PMC<id>.1.pdf`.
- **Tool:** `uv run tools/fetch_pdf_fixtures.py` — dev-time only, never imported by
  tests; prints a manifest (object URL, byte size, sha256) and exits non-zero if any
  paper fails. Re-run it any time to re-fetch; the recorded URLs allow manual fetch.
- **License check:** the OA-dataset metadata JSON for each `PMC<id>.1` version reports
  `license_code: CC BY`, matching the `<!-- source -->` comments.

Tests never touch the network (autouse blocker in `tests/conftest.py`); the PDFs are
committed fixtures, and `tests/extract/test_pdf_fixtures.py` pins the set (five files,
≥ 10 KiB each).

## Signal survey (2026-09-22, `tools/pdf_signal_survey.py`)

Reconstruction floor for the `frontend` aspect, measured on **PMC13134363** (Cureus,
largest abstract label set) with `uv run --with pypdf python tools/pdf_signal_survey.py`:

| Signal | Result |
|---|---|
| PDF pages | 21 |
| PDF text chars (per-page, raw) | 71,572 |
| `##` heading recovery (unique) | **8/8 (1.000)** |
| Table cell recovery | **490/506 (0.968)** |
| Table line recovery (≥ 1 cell) | **110/110 (1.000)** |
| Table line recovery (majority of cells) | **110/110 (1.000)** |
| Abstract prose | readable verbatim on page 1 |

Heading recovery at 1.0 and table recovery well above 0.5 support the **≥ 90%
whole-paper recovery floor** (PRD M3). Residual: 16 of 506 table cells did not
recover verbatim (likely line-wrapped or styled cells); the frontend aspect must
treat cell-level gaps as expected, not as missing tables. One conversion quirk
already surfaced: the JATS→Markdown conversion glues the "Abstract" label to the
prose ("AbstractThis review…") where the PDF has a line break — the frontend must
normalize label gluing, not rely on verbatim matches.

## Fixture exclusions (M4)

**No fixture is currently excluded.** The one fixture that could not clear the
≥ 90% whole-paper claim-id recovery floor (PRD M4) after the column-aware
reconstruction — **PMC12780771 (Oxford)** — cleared it on 2026-09-22 with the
last-mile fixes, at **abstract 6/6 (1.000), whole-paper non-table 25/25
(1.000)**. The section stays because the seam suite asserts it documents any
excluded PMCID with a measured rate (`tests/extract/test_pdf_seam.py`) — with
an empty exclusion set that assertion is vacuous but the section remains the
place this state is recorded, never silent.

**What was wrong, and what the fixes actually were.** The M4 note named two
causes for Oxford's four missing claims: a pypdf CFF font gap ("the `and
IQCODE (0-5, higher` fragment is undecodable without fontTools") and a
sentence broken across a page break and a table ("was detected more than 500
times out of 1000 runs"). Investigation falsified the first hypothesis and
refined the second:

- **The CFF attribution was wrong.** pypdf does emit its `fontTools is
  required` warning on this file (a CFF Type1 math-symbol font inside a form
  XObject), but converting with fontTools installed produces **byte-identical
  output** — only the warning line disappears. The fontTools dependency was
  therefore **not** added: it fixes nothing, and `pypdf` remains the one
  pinned runtime dependency. The actual mechanisms were three pypdf/publisher
  artifacts, all fixed deterministically in the converter (no new deps):
  1. The publisher splits `IQCODE` into `IQC` + `ODE` (and `I` + `QCODE,`)
     with a kerning move between the halves; pypdf reads the gap as a word
     boundary. The converter rejoins an all-caps pair when the paper itself
     writes the concatenation as a token elsewhere in the document
     (`IQCODE` is written whole five times) — a corpus-grounded rule that
     never fires on a genuine two-word pair (`AUC AUPRC`, `CC BY`).
  2. The table rows and header lines span the gutter; splitting them at the
     column boundary leaked the right-half cells into the right column as
     stray value prose between the sentence halves. Table-structure lines
     (a table region, or a crossing line whose two sides map to several
     distinct columns) now stay whole.
  3. The running-head page-number fragment (`| 243`) survived the furniture
     drop (it does not repeat — the number changes); it is now dropped as
     furniture, and the superscript citation numeral (`runs. 9`) glues to the
     period it belongs to (`runs.9`).
- **The "page break" was actually a table plus a column split on one page**:
  the sentence ends the left column of page 7 (`...more than 500 times`) and
  continues at the top of the right column (`out of 1000 runs. 9 ...`), with
  Table 3 between them in the emission.

Measured 2026-09-22 with the seam suite's pinned arithmetic (denominator = distinct
Markdown-path `Claim.id`s outside table cells; numerator = those ids recovered by the
PDF path by id; table cells excluded from the bar and counted separately, PRD
criterion 2):

| PMCID | Abstract recovery | Whole-paper recovery (non-table) | Reason |
|---|---|---|---|
| `PMC12780771` | 6/6 (1.000) | 25/25 (1.000) | formerly M4-documented at 21/25 (0.840) |

**Survey-vs-reality gap, stated honestly:** the original signal survey measured
heading and table recovery on **PMC13134363 only** (Cureus, single-column) and set
the ≥ 0.90 floor from that paper. The other four journals (Oxford, MDPI × 2,
Springer) typeset in **two-column interleaved content streams**, and the column
reconstruction (2026-09-22, the `columns` aspect) plus the last-mile fixes
(2026-09-22) close that gap: **all five fixtures now clear both floors** —
**PMC13134363** abstract **19/19 (1.000)**, whole-paper non-table **19/19
(1.000)**; **PMC13298092** abstract 2/2, non-table **52/54 (0.963)**;
**PMC13363872** abstract 9/9, non-table **9/9 (1.000)**; **PMC13332965**
abstract 0/0 (the Markdown fixture's abstract carries no quantitative claim —
vacuous), non-table **38/41 (0.927)**. The layout dimension (column geometry,
per-page y direction, running-head/footer bands, publisher word-splits) is now
measured, not assumed. Nothing in this section is a verdict about the papers.

## Egress posture

These papers came **in**. Nothing went out: no paper text, no repository content, and no
user data was sent anywhere. The fetch was a read of a public open-access endpoint,
authorized explicitly, and the files now sit on local disk like any other fixture. This
is consistent with `CLAUDE.md` constraint #2, which governs *egress* — never sending a
paper or dataset to a service the user did not authorize.

## Scope of labelling

Labelling covers the **abstracts** only. Headline quantitative claims live in abstracts
by definition, and exhaustive labelling of five full texts (~13,500 digits) would be
neither tractable nor more informative for the question the rule must answer. The full
text is retained because candidate extraction, table parsing and section hints are
exercised against whole documents even where labels are not.
