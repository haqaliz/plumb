# Plumb: publishing and ethics policy

Plumb points at real, named papers and reports which of their quantitative claims its *own*
artifacts failed to reproduce. That is a claim about someone's published work, so this document
states — before any finding is published — what Plumb asserts, what it refuses to assert, and how
an author responds. It is deliberately conservative; §5 lists what we will not do even when the
tool says we could.

The one-line rule: **a reproduction discrepancy is not an accusation of misconduct, and nothing
leaves this project as a finding until a human has reviewed it against its own signed bundle.**

---

## 1. The verdict vocabulary, and its limits

| Verdict | What it asserts | What it does **not** assert |
|---|---|---|
| `REPRODUCED` | The paper's number was re-derived, from the paper's own artifacts on the verifier's compute, within the precision the paper itself wrote | That the science is correct, novel, or meaningful |
| `WITHIN-TOLERANCE` | Same, with a non-zero delta inside a declared tolerance band | That the tolerance is the right one — the paper or the verifier declared it |
| `DIVERGED` | The artifact's **own run** produced a value that contradicts the paper's own claim, at the paper's written precision | That the paper is wrong, that the authors erred in good faith, or that the result is not real |
| `UNVERIFIED` | We could not decide — the repo would not run, the claim would not bind, the artifact was stale, or the tolerance could not be set | Nothing it has to say is evidence either way. It is the honest default and is **never** rendered as `REPRODUCED` |

Three invariants govern every verdict, and each is pinned by a test in the repo:

1. **Execution decides, never a model.** A model may extract a claim or propose how to bind it.
   Only re-execution may produce a verdict (`CLAUDE.md` constraint #1).
2. **No harness failure becomes a `DIVERGED`.** A run-side cause governs first: if the artifact
   will not run, the claim is `UNVERIFIED`. A discrepancy that could plausibly be *our*
   environment or *our* binding resolving to `DIVERGED` is not permitted by construction.
3. **A stale result is never parsed.** An output whose bytes predate the run is `UNVERIFIED`,
   never read (`CLAUDE.md` constraint #5).

The consequence for a reader: a `DIVERGED` means *the code you shipped does not print the number
you reported*, at the precision you reported it. It does not mean more than that, and we will not
let it.

---

## 2. When a `DIVERGED` is publishable

A `DIVERGED` is **not** a finding. It becomes a candidate finding only when all four hold:

1. **It replays.** The signed bundle reproduces the verdict byte-identically for a third party who
   was not involved in producing it.
2. **The binding is honest.** The value was read from the artifact the claim is about, through a
   locator a reviewer can check by eye, not from a lookalike table or a neighbouring column.
3. **The cause is the artifact, not the harness.** Environment drift, a missing dependency, a
   non-deterministic run, or a coarse output precision all resolve to `UNVERIFIED` or to a
   refutation — never to a published discrepancy.
4. **A human reviewed it.** Owner review of the specific claim, recorded with its label.

Only then is it reported, framed as a reproduction discrepancy, with the bundle attached and the
method published.

Prepared findings live in [`docs/findings/`](findings/) and are **unpublished** until the
human checklist in each note is complete: owner sign-off, author contact, the reply window, and a
recorded outcome. The note states the claim id, the reported and re-derived values, and the replay
command, and a test pins its numbers to the signed bundle.

### The case that defines the process: Perrin

Plumb's own corpus contains the strongest argument for this policy. On Perrin
(arXiv:2401.11842), the tool flagged **14 `DIVERGED` claims**. Owner review refuted **all 14**:
the artifact is not run-to-run reproducible at the paper's *written* precision — the survival
draws use unseeded worker RNG, three full runs moved every value (up to 0.017) and flipped four
verdicts, and the sampling noise (~0.005–0.010) exceeds the precision the paper wrote down
(0.001). The labels in the corpus record that as **a reproducibility finding about the artifact,
not a paper error**, and it was never published as a discrepancy.

That is the system working: the tool reports what the run did; the review decides what it means;
the corpus keeps both, so the honest number reflects the refutation instead of hiding it.

---

## 3. Label authority

Every pooled figure names who labeled the cases it rests on:

- **`owner`** — a label set by this project's maintainer, reviewing the claim against its bundle.
  This is the authority behind the `1/15` precision figure today.
- **`third-party`** — a label set by someone independent of the project. The corpus report
  distinguishes the two and never pools them silently.

Labels are transported into the corpus, never invented by the tool. A case that has not been
reviewed is **unlabeled**, and unlabeled cases are excluded from precision and recall rather than
counted as either.

---

## 4. Right of reply and correction

An author or reader who disputes a published finding gets a substantive answer, not a debate:

1. **Open an issue** at <https://github.com/haqaliz/plumb/issues> naming the finding and the
   specific claim. The signed bundle is the shared object of discussion.
2. **The bundle settles the mechanical questions.** Either the record replays as published or it
   does not. A replay that fails is a defect on our side and is fixed as one.
3. **A refuted finding is corrected, not edited away.** If review shows the discrepancy was an
   artifact of our environment, our binding, or the code's own non-determinism, the finding is
   marked refuted in the corpus — exactly as Perrin's 14 are. The corpus keeps the original
   verdict and the refutation side by side; the published claim is withdrawn or amended, with a
   note that says what changed and why.
4. **Retraction.** If a finding was published and is later refuted, the correction says so plainly
   and links the refutation. Silent edits are not an acceptable outcome.

Reproduction discrepancies are often the *interesting* case — an unseeded RNG, a stale committed
output, a table that no longer regenerates. The process above exists so a real one survives
scrutiny and a false one cannot.

---

## 5. What we will not do

- **We will not call anyone's work fraudulent, fabricated, or misconduct.** Plumb reports
  reproduction discrepancies; it has no standing to judge intent and does not try.
- **We will not publish a model's opinion as a finding.** An LLM judge's guess about correctness
  is not a verdict, and Plumb's verdicts are not produced that way.
- **We will not publish a finding that does not replay** for an independent third party from the
  bundle alone.
- **We will not egress a paper or its data.** Verification runs on the user's compute; only hashes,
  metadata, and the verdicts a user chooses to publish leave the machine (`CLAUDE.md`
  constraint #2). Any LLM assist is BYOK, disclosed, and off by default.
- **We will not report extraction conformance as coverage.** C1's conformance scores are reported
  as conformance, never as the fraction of a paper's claims we captured.
- **We will not let a number look better than its denominator.** Precision, recall and coverage are
  always printed with the count they rest on and the authority behind the labels.

---

## 6. Where this policy is enforced

| Rule | Enforced by |
|---|---|
| Execution decides, never a model | `src/plumb/verify/`; a model cannot assign a verdict |
| No harness failure → `DIVERGED` | `tests/verify/test_false_diverged_guard.py` (mutation-checked in-suite) |
| A stale output is never read | the freshness guard in `src/plumb/run/capture.py`, mutation-checked |
| Claims re-grounded against the paper | the admission gate is the only constructor of a `Claim` |
| Findings replay for a third party | the signed bundle (`src/plumb/bundle/`), replayed by `tools/bundle_replay.py` |
| Figures carry denominators and authority | `plumb corpus report` |
| The honest number is published, refutations included | `README.md` "The number so far"; [`METHOD.md`](METHOD.md) |
