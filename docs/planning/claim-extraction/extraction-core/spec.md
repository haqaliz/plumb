# Aspect 2 — `extraction-core`

Parent: [`../prd.md`](../prd.md) · Covers **M3, M5, M11, M12, M15** · Depends on:
aspect 1 (`claim-schema`) · Gates: nothing (aspect 3 is independent of it).

## Problem slice

Turn paper text into the *right* claims. This aspect owns the single most consequential
decision in C1 — **what counts as a headline quantitative claim** — and the structural
guarantee that nothing becomes a `Claim` without deterministic grounding.

**Outcome:** an extractor whose selection rule has been scored against labels it did
not author.

## In scope

1. **Blind fixture set first (M15).** Hand-label the headline claims of ~5 real papers
   and **commit the labels before writing the selection rule.** This ordering is the
   deliverable, not a suggestion.
2. **Selection rule (M3).** A number is admitted only if it is (a) asserted by *this*
   paper about its own results, (b) carries a named metric, (c) appears in abstract,
   results, or a table. Rejection list, one test each: publication/citation years,
   page/figure/table/equation numbers, version strings, grant/DOI/ORCID digits,
   reference-list numerals, hyperparameters, axis labels.
3. **Admission gate as sole constructor (M5).** No code path constructs a `Claim`
   except through deterministic grounding against the paper text.
4. **Ungroundable → non-claim record with a named cause (M4).** Never a `Claim`, never
   a verdict, never silent.
5. **Markdown table parsing (M12).** `CAPABILITY_ROADMAP.md:25` puts table parsing in
   the deterministic core.
6. **`StudyParameter` population (M11).** Reported N extracted here, kept out of the
   claim denominator.
7. **Selection scoring.** Precision/recall against the blind labels, reported.

## Out of scope

Serialization, hashing, dedup (aspect 3). The record's shape (aspect 1). PDF, DOI, the
BYOK proposer — but M5 preserves the seam the proposer will later plug into.

## Acceptance criteria (failing tests first)

- **Ordering is enforced:** the blind label fixtures are committed in an earlier commit
  than the selection rule. (Verifiable in `git log`; state it in the PR.)
- Each rejection category has a test asserting the number is **not** emitted as a claim:
  a publication year, a figure number, a version string, a DOI digit sequence, a
  reference-list numeral, a hyperparameter, an axis label.
- A related-work number attributed to another paper is **not** emitted as this paper's
  claim (guardrail `CLAUDE.md` #3 / **R4**).
- A value that cannot be grounded in the paper text yields a **non-claim record with a
  named cause** — asserted positively, not by absence.
- No `Claim` can be constructed bypassing the admission gate (test the seam directly).
- A Markdown table's cells are extracted with correct `location` spans.
- Reported N is emitted as `StudyParameter`, never as `Claim`.
- Selection precision/recall is computed and reported against the blind fixtures.

## Risks

- **R3** Med/High (`ROADMAP.md:58`) — this aspect *is* R3. M15 is the mitigation.
- **R1** High/High (`ROADMAP.md:56`) — over-extraction buries real claims in
  `UNVERIFIED` downstream; under-extraction inflates coverage. Both are selection
  errors, and both are invisible without the blind scoring.
- Guardrail `CLAUDE.md` #4: the admission gate, not the regexes, is the part that gets
  better as models improve. Keep it the sole constructor even though the proposer is
  out of scope.

## Open questions

- Five blind papers can show the rule is wrong; they cannot show it is right. The rule
  stays provisional until the first real corpus run.
- Whether a "named metric" requires a controlled vocabulary or free text — decide in
  `tech-plan`.

## 🔴 Unrecognised sample-size forms fall *through*, not out (part 2 must fix the class)

A sample size the recogniser does not know does not get dropped — it admits as a
**`Claim`**, landing a permanently unbindable number in the coverage denominator the
Phase 0 gate turns on. `_n_ = 412` did exactly this and is now fixed, but **the fix
closed one spelling, not the class.** These still fall through:

`n of 412` · `sample size of 412` · `n₁ = 412` · a table cell `| n | 412 |`

A per-spelling recogniser will always lag the ways papers write things. **The durable
mitigation is M3's requirement that a claim carry a named metric** — `n` cannot supply
one, so a correct selection rule rejects all of these structurally rather than by
enumeration. Part 2 owns this. Until then, treat the coverage denominator as
*optimistic*: it may contain sample sizes wearing the wrong type.

Note the general lesson, which applies beyond N: *"the safe direction is a false
negative"* holds only when something downstream catches the miss. With no selection
rule built, nothing does.

## Composite values are one candidate (measured 2026-09-21, fixed same day)

`Candidate.text` used to be a bare number, so the `0.001` of `p < 0.001` would have
admitted as a `Point` asserting *p = 0.001* — a value the paper never wrote, and one
against which a re-derived `0.0009` would read as a contradiction. The gate refused it
as `partial_value` rather than inventing it, which meant **bounded values could not
become claims at all**. `extract_candidates` now emits the whole notation as one
candidate, so `Bound`, `PlusMinus`, `Range`, `Interval` and `Approximate` are reachable
from real extraction for the first time.

**Measured across the five fixture papers, before → after:**

| | before | after |
|---|---|---|
| candidates | 4900 | 4748 |
| `partial_value` refusals | 538 | 310 |
| `Bound` / `PlusMinus` / `Range` / `Interval` / `Approximate` | 0 | 55 / 22 / 58 / 36 / 18 |
| candidates `parse_value` cannot read | 0 | 0 |

The residual 310 is almost entirely the digit/comma-adjacent class (305 superscript
citation runs like `States.2,3`), which is not composite notation and is correctly
refused. One composite is still refused, correctly: `>= 3.5` in `(>= 3.5.0)` cuts a
three-part version string.

Three defects surfaced while measuring this, all fixed:

- 🔴 **A sign-flipped value was reaching the record.** The sign rule attached `+`/`-`
  whenever nothing *word-like* preceded, and `%` is not word-like — so `0.4%-1.7%`
  yielded `-1.7`, a negative number from a paper reporting a positive one. It grounded,
  it parsed, and `admit` had no cause to refuse it. `%` now blocks sign attachment.
- 🔴 **`Interval` was unreachable, and the bracketed grammar was written from a wrong
  assumption.** Of 29 confidence intervals across the five papers, **none** is
  bracketed: 16 are `95% CI: 0.4%-1.7%`, 7 `95% CI 1.66–2.54`, 6 `95% CI: -5.432,
  -4.092`, plus 8 `CrI` credible intervals. Meanwhile *every* bracketed numeric pair in
  the corpus is a citation (`[30,31]`) or a degrees-of-freedom pair (`(6,12)`).
  `parse_value` now reads the marked forms, and an explicit `CI`/`CrI` marker — not the
  bracket — is what identifies an interval. This also closed a `Point(95)` escape: the
  confidence level used to stand free as a reported value of its own.
- 🟡 **`_is_a_fragment`'s digit-before guard over-fired**, refusing five real bounds
  whose name ends in a digit (`I²<50`, `ΔR2≈0.38`). It now applies only to spans that
  start like a number, which is the only shape it can describe.

## Known limits of candidate extraction (recorded 2026-09-21)

Both are safe to defer **only because the first label set covers abstracts only**, and
every one of the five fixture papers has a literal `## Abstract` heading. Neither
affects the labels; both affect the selection rule's reach and must be revisited when
labelling extends beyond abstracts.

- 🟡 **`section_hint` mixes two axes.** `abstract` / `results` / `references` / `other`
  say *where in the document*; `table` says *what container*. `table` wins the override,
  so a number in a table inside `## References` reports `table` and its section is
  unrecoverable. If both facts are ever needed, that is two fields (`section_hint` +
  `container`) — cheaper to split before table candidates are labelled than after.
- 🔴 **The heading map matches only 17 of 119 real headings** across the five fixtures.
  Two papers yield **zero** `results` candidates: their sections read
  `## 5. Per-Dataset Analysis Results` and `## Review`. Matching is exact by choice —
  word containment would add 5 headings but mislabel 3 table captions
  (`### Table 5. … test results …`) as `results`, and honest `other` beats a confident
  guess.

  **Consequence for M3's criterion (c)** ("appears in abstract, results, or a table"):
  with this coverage, `results` is unreliable, so in practice the criterion reads
  "abstract or table" on real papers. The rule must not lean on `results` until the
  map is widened, and the widening needs evidence about real heading forms rather than
  a guess.

## Inherited from aspect 1 (decided 2026-09-20)

- **Hyphen ranges are unsupported — outside an interval marker** (amended
  2026-09-21). `parse_value` accepts only en/em dashes as range separators; `12-15`
  returns `None`, because an ASCII hyphen is ambiguous against a signed or subtracted
  value. That still holds everywhere except after an explicit `CI`/`CrI`, where the
  evidence asked for above arrived: 16 of the corpus's 29 confidence intervals are
  written `95% CI: 0.4%-1.7%`, and after the marker no subtraction reading is
  available, because the notation has already said what it is. The hyphen is scoped to
  exactly that context and nowhere else; the general recall gap is unchanged and still
  surfaces in blind-label scoring.
- **Units must be separated from the value before `parse_value` is called.** It
  tolerates only a trailing `%`; `0.87 kg` returns `None`. General units belong in
  `Claim.units`. This coupling is this aspect's responsibility — accepting arbitrary
  trailing tokens in the value would silently swallow a unit into the number.
- **`parse_value` returning `None` is the caller-decides seam for M4.** An unparseable
  value is data, not a programming error; this aspect decides whether it becomes a
  non-claim record with a named cause.
