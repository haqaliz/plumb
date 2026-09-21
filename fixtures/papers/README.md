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

| File | DOI | Title |
|---|---|---|
| `PMC12780771.md` | 10.1177/08919887251355507 | Improving accuracy in the estimation of probable dementia in racially and ethnically diverse populations |
| `PMC13134363.md` | 10.1186/s12888-025-07354-6 | Global Autism Spectrum Disorder Prevalence Estimates and Associated Covariates |
| `PMC13298092.md` | 10.3390/diagnostics15182386 | Diagnostic Accuracy of Auricular Morphometry in Sex Estimation: A Logistic Regression approach |
| `PMC13332965.md` | 10.1186/s13059-025-03797-y | Within-sibling attenuation of polygenic risk score accuracy |
| `PMC13363872.md` | 10.3390/jimaging11090318 | Understanding the Performance of Deep Computer Vision Models: A Symbolic Regression approach |

DOIs are recorded from the source metadata; verify against the `<!-- source -->` comment
in each file before citing one.

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
