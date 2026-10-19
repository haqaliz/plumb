# Plumb: the method and the number

Plumb's credibility rests on one number, and this page exists so that number is read with its
denominator, its label authority, and its refutations attached — not quoted on its own.

**The number today: precision and recall `1/15` against owner labels, over 3 real papers and 133
claims.** One republishable discrepancy out of fifteen flagged, because fourteen were the
artifact's own run-to-run noise and were refuted on review.

If that reads as a weakness, read [§5](#5-why-14-of-15-were-refuted-it-is-the-system-working)
before quoting it. It is the honest measurement of a verifier that refuses to launder a
reproducibility problem into a paper error.

---

## 1. What is being measured

The unit of work is a **claim**: a quantitative statement the paper makes, with its reported
value, units, metric, and location. Plumb's spine is:

> intake (paper + pinned checkout) → run the repo's own artifacts → capture what the run produced
> → bind each claim to a re-derived value → decide a verdict → bank the case → sign a replayable
> bundle.

The measurement is over **cases**, where one case is one paper verified end to end. Every
(claim, re-derived value, verdict, cause) is banked write-once into the discrepancy corpus, and a
human labels the flagged discrepancies.

What is **not** measured here: whether a paper's science is correct, whether an unflagged claim is
true, or how many errors exist in the literature. This is a panel of three runnable papers, and
it is reported as such.

---

## 2. The panel

All three papers were selected by a fixed rule written **before** selection, and every record
replays byte-identically from its committed bundle.

| Paper | arXiv | Claims | REPRODUCED | DIVERGED | UNVERIFIED | Reviewed |
|---|---|---|---|---|---|---|
| AgroDesign | `2603.09041` | 86 | 85 | 1 | 0 | 1 confirmed |
| Perrin | `2401.11842` | 16 | 2 | 14 | 0 | 14 refuted |
| Burtsev (rcai) | `2609.00137` | 31 | 30 | 0 | 1 (`NO_BINDING`) | — |

- **AgroDesign** — its single confirmed discrepancy is a Shapiro-Wilk `p` reported as `0.034`
  that its own code computes as `0.03455`, unchanged in a paper-era environment. That is the one
  republishable finding.
- **Perrin** — a reproducibility finding, not a paper error; see §5.
- **Burtsev** — the first notebook-computed paper through the spine: 30 of 31 claims bound through
  `notebook_cell` locators, one `UNVERIFIED` (`NO_BINDING`), zero `DIVERGED`, 70 s wall.

Provenance, licences and the reproduction commands for each case live beside the records in
[`fixtures/gate/`](../fixtures/gate/).

---

## 3. The report, verbatim

Produced by `plumb corpus report` over the three banked cases:

```
CASE                     | CLAIMS | BOUND | REPRODUCED | WITHIN-TOLERANCE | DIVERGED | UNVERIFIED | LABELED | CONFIRMED
-----------------------------------------------------------------------------------------------------------------------
3f7f808d2861cff8fe838a5… | 16     | 16    | 2          | 0                | 14       | 0          | 14      | 0
941b556bea2792b1c24abd9… | 86     | 86    | 85         | 0                | 1        | 0          | 1       | 1
db99db77e4e15da01fdd2b7… | 31     | 30    | 30         | 0                | 0        | 1          | 0       | 0
total (3 cases)          | 133    | 132   | 117        | 0                | 15       | 1          | 15      | 1

  coverage: 132/133 bound
  precision: 1/15 (owner)
  recall: 1/15 (owner)
```

Case ids are content hashes; `LABELED` counts the flagged discrepancies a human reviewed, and
`CONFIRMED` counts those the review upheld.

---

## 4. How to read `1/15`

- **Denominator.** 15 `DIVERGED` verdicts across the panel. One was confirmed on review. The other
  14 were refuted — the corpus records the refutation rather than hiding the flag.
- **Authority.** `(owner)` means the maintainer labeled the claim against its bundle. Third-party
  labels are a separate authority and the report never pools them silently. Unlabeled cases do not
  enter precision or recall.
- **Coverage is separate.** `132/133 bound` says how many claims could be bound to a re-derived
  value. It is not the same as precision, and it is not a claim about extraction coverage.
- **This is a panel, not an estimate.** Three papers, deliberately runnable ones. Do not read
  `1/15` as "one in fifteen findings is real" in general; read it as what this panel, with these
  labels, produced.

---

## 5. Why 14 of 15 were refuted (it is the system working)

Perrin's artifact is **not run-to-run reproducible at the precision the paper writes down**:

- the survival draws use unseeded worker RNG;
- three full runs moved every claim's value, with a spread up to `0.017` and **four verdict
  flips**;
- the binomial sampling noise (~`0.005`–`0.010`) exceeds the paper's written precision (`0.001`).

So Plumb's `DIVERGED` verdicts were **mechanically correct about the run** and **wrong as
findings about the paper** — the run does not hold still enough for the paper's own precision. The
review recorded exactly that, and the corpus marks all 14 refuted. Nothing was published as a
paper error.

This is the distinction the whole project is built on:

| Question | Answer for Perrin |
|---|---|
| Did the artifact reproduce its numbers? | No — not at the written precision. |
| Is the paper's reported number wrong? | Unknown; the artifact cannot settle it. |
| What does Plumb report? | A reproducibility discrepancy, refuted as a paper-error finding. |

If Plumb had counted those 14 as confirmed, its precision would read `15/15` and every one would
be indefensible. The number is `1/15` because the review is real.

---

## 6. Reproduce the number

The corpus is local and write-once (`corpus/local/`, gitignored). From a checkout:

```bash
# bank each committed record (write-once; a re-bank is a no-op for the same case)
uv run plumb verify --from-record fixtures/gate/agrodesign --bank
uv run plumb verify --from-record fixtures/gate/perrin --bank
uv run plumb verify --from-record fixtures/gate/rcai --bank

# pool coverage, precision and recall, with denominators and label authority
uv run plumb corpus report
```

Each record's `labels.json` carries the human labels; the report refuses a tampered or unreadable
case rather than producing a partial number. The signed AgroDesign bundle verifies offline and
replays byte-identically from a clean clone (`tools/bundle_replay.py`, `bundles/README.md`).

---

## 7. Known limits (read before trusting a coverage claim)

- **The runnable-paper space is thin.** Most published computational notebooks do not reproduce at
  all (a widely cited ~3.2%), and many papers ship no code. A fixed-rule panel search of four
  candidates produced one additional runnable paper. Coverage will look low because the input
  space is low, and that is itself part of the finding.
- **Figure-with-data locators are not built.** A result that exists only in a figure is
  unreachable; it becomes `UNVERIFIED`, never a silent pass.
- **The no-code path (C7) is not built.** For a PDF-only paper the honest answer today is "cannot
  verify", not "verified".
- **C1 extraction is a deterministic rule, not an oracle.** On AgroDesign it recovers 86/86 of a
  curated claim set — a *conformance* score to that rule — and on Burtsev its conformance is 0/31.
  Conformance is reported as conformance and never as coverage.
- **Live mode is expert mode today.** `--bindings` is hand-written; there is no binding proposer
  yet. The launch rides the replay demo, not self-serve verification of an arbitrary paper.
- **One runtime dependency, no network in tests.** The offline suite pins determinism; the number
  above is reproducible without a network.

---

## 8. The obvious hostile question

> *"So your tool was wrong 14 out of 15 times?"*

No. The tool reported, correctly, that the artifact's own run did not reproduce its reported
values at the written precision. The **label** refuted the discrepancy, because the artifact does
not run stably enough for those values to be paper errors. That distinction is the product: a
verifier that reported `15/15` here would be guessing. Plumb reports what the run did, records the
refutation, and publishes both.

If you want a number to be skeptical of, be skeptical of any reproduction tool that reports high
precision without showing its refutations. Ours shows them.
