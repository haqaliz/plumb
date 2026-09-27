# Understanding — C1 claim recovery on the gate paper

Deep dig for `docs/planning/_card/issue.md` (2026-09-27). All numbers below are from an
in-memory probe on `fixtures/gate/agrodesign/paper.pdf` through `extract_claims`, matched to
the 86 curated claims **by span**, not by `Claim.id` (see contradiction 1).

## What the work really is

The brief names three causes. The probe says one of them is the whole recall gap, and the
work is mostly *precision and identity*, not recall.

| Probe | Recovered (span match) | Claims emitted | Unique ids |
|---|---|---|---|
| As built | 0 / 86 | 0 | 0 |
| + `"experimental validation"` → `results` in `_HEADING_SECTIONS` | **85 / 86** | 99 | **90** |

- **Cause 1 (section) is the recall gap, entirely.** Every one of the 86 is refused
  `outside_sections` today; mapping the one heading recovers 85. Sub-sections the converter
  failed to mark as headings (4.2, 4.4) inherit from `# 4` already.
- **Cause 3 (glued `145.333<0.001`) is not a gap.** Tokenization already splits it into
  `145.333` and the bound `<0.001`; both recover.
- **Cause 2 (whitespace table rows) is not a recall gap but an identity gap.** Table cells
  recover as prose, with the row label as metric (`Residual`, `Nitrogen`). Nine claims share
  an id: `Nitrogen 2 433.500 433.500<0.001` gives MS and F the same `(text, metric, units)`;
  every table's Residual DF `16`/`12` collides; the first row's metric is
  `Source DF MS F p-value Treatment`. C4 binds by claim — an id naming two cells is
  ambiguous.
- **The one miss** is a span convention, not a failure: curated `p <0.001` (§4.4) vs
  extracted `<0.001` with metric `p` — the same `Bound`.

## Precision: the 14 non-curated claims (once §4 is `results`)

| Class | Instances | Danger |
|---|---|---|
| `p ¡ 0.001` read as **Point 0.001**, metric `p ¡` | 2 | **High** — asserts p = 0.001, a value the paper never wrote; a run's 1e-10 would read `DIVERGED`. `¡` is LaTeX OT1's rendering of `<` |
| Section-number in a heading line (`# 4`, `## 4.1`, `4.3`, `4.6`) | 4 | metric `#`/`##` — garbage |
| PDF page-number line (`8`, `11`, `13`, `15`) | 4 | furniture, metric from neighbouring text |
| Significance level `atα= 0.05` | 2 | a design input, not a result |
| List-item marker `1.` | 1 | enumeration |
| (the `<0.001` of the one miss) | 1 | true claim, span convention |

## Constraints found

- **The converter's AgroDesign output is frozen.** `verify_bundle` re-runs `pdf_to_markdown`
  on the bundled paper and re-admits every claim at its recorded offsets
  (`src/plumb/bundle/verify.py:189,241`), and `claims.json` stores offsets. Any converter
  change to this paper's text breaks the signed bundle. Fixes belong in `extract/`
  (candidates, selection, gate), not `pdf/`.
- **`_HEADING_SECTIONS` is deliberately literal** (`candidates.py` docstring): each title is a
  deliberate edit with a test. A fuzzy rule (`endswith "results"`) would flip
  PMC13363872 `## 5. Per-Dataset Analysis Results` and risks `## 4. Experimental Setup`
  (hyperparameters) — the literal list is the right mechanism.
- **The blind set is abstract-only** (73 rows); a heading change cannot move it, new
  rejection cues can. The PDF↔Markdown seam test guards the fixtures.

## Contradictions with the brief (flagged, not papered over)

1. **"Matched by `Claim.id`" cannot work.** `Claim.id` hashes `(text, metric, units)`
   (`claim.py:61`); the curated metrics are hand-written (`Table 1 crd ANOVA Treatment DF`).
   Recovery must be matched by location + parsed value.
2. **Cause 3 is already handled**; cause 2 matters for identity, not recall.
3. **The real risk moved from recall to precision (R3):** the section fix alone *creates*
   two false Point claims out of `p ¡ 0.001`. Shipping recall without the precision fixes
   would be worse than 0/86.

## Open questions (for the PRD)

- Table identity: disambiguate whitespace-row cells how, without touching the converter?
- `¡`/`¿`: refuse (named cause) vs repair as `<`/`>` (a repair can't change the text, so the
  claim text wouldn't parse — refusal is the only representable option without converter work).
- Precision floor on this paper, and whether new causes enter the closed vocabularies.

Place in pipeline: **C1 extract** only. No verdict is touched; execution still decides.
