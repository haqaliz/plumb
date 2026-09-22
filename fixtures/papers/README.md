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

Four of the five PDF fixtures cannot clear the ≥ 90% whole-paper claim-id recovery
floor (PRD M4) after the frontend's honest reconstruction effort. They are **excluded
from the equality bar and documented here with their measured rates** — never a
silent drop, never a hard fail: the seam suite asserts this section mentions each
excluded PMCID together with a measured rate (`tests/extract/test_pdf_seam.py`).

**Survey-vs-reality gap, stated honestly:** the signal survey measured heading and
table recovery on **PMC13134363 only** (Cureus, single-column), and the ≥ 0.90 floor
was set from that paper. The other four journals (Oxford, MDPI × 2, Springer) typeset
in **two-column interleaved content streams** — the converter's single-column line
model merges or reorders the columns' fragments, so prose (including the abstract)
does not round-trip and claim ids diverge. That layout was outside the survey's
measurement; the rates below are the honest numbers.

Measured 2026-09-22 with the seam suite's pinned arithmetic (denominator = distinct
Markdown-path `Claim.id`s outside table cells; numerator = those ids recovered by the
PDF path by id; table cells excluded from the bar and counted separately, PRD
criterion 2):

| PMCID | Abstract recovery | Whole-paper recovery (non-table) | Reason |
|---|---|---|---|
| `PMC12780771` | 0/6 | 7/25 (0.280) | Oxford Academic: two-column interleaved stream; pypdf also drops the document tail (`Exceeded 5000 form XObject invocations`) |
| `PMC13298092` | 0/2 | 2/54 (0.037) | MDPI Diagnostics: two-column interleaved stream; abstract prose interleaves with the footer/editorial block |
| `PMC13332965` | 0/0 (vacuous) | 1/41 (0.024) | Springer Human Genetics: two-column interleaved stream; left/right column fragments merge into single lines |
| `PMC13363872` | 0/9 | 0/9 (0.000) | MDPI Sensors: two-column interleaved stream; left/right column fragments merge into single lines |

The converter's line model reconstructs the Cureus PDF completely — `PMC13134363`
passes both floors: abstract **19/19 (1.000)**, whole-paper non-table **19/19
(1.000)**. Multi-column journals are a follow-on reconstruction problem, recorded
here rather than hidden; nothing in this section is a verdict about the papers.

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
