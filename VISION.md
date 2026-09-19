# Plumb: Vision

> A published result you cannot re-run is not a finding. It is a file that once printed a number.

---

## The bet in one sentence

The valuable, defensible problem in research integrity is not *guessing* whether a paper is
wrong — an LLM can do that, badly. It is **re-deriving the paper's own claims from the paper's
own code and data, by execution, and showing exactly which ones do not hold.** Plumb is the
harness that does that around *any* paper, on the user's own compute.

---

## Why now

- **The correction layer is in crisis.** Retractions passed ~10,000 in 2023 and keep rising;
  peer review is buckling under submission volume and AI-generated manuscripts.
- **Buyers are already paying.** Elsevier rolled Check Integrity across ~2,000 journals
  (Mar 2026); Springer Nature runs automated pre-editor checks; the STM Integrity Hub and a
  field of third-party vendors are expanding. The budget exists.
- **The obvious fix — an AI that reads and opines — measurably does not work.** A 2026 JMIR
  study found freely available AI tools cannot reliably flag even *retracted* literature;
  frontier models hit ~6.1% precision on real errata-worthy errors (SPOT, arXiv 2505.11855).
  That unreliability is the opening: the only trustworthy signal is **re-execution**.
- **The reproducibility floor is on the ground.** ~3.2% of published notebooks reproduce. The
  headroom is enormous, and the story ("AI catches real, verifiable errors in the literature")
  is a press magnet whenever a finding is genuinely reproducible.

---

## The founder's unfair advantage

The moat is **engineering** — reproducible environment building, execution capture,
claim↔artifact binding, deterministic re-derivation, a signed replayable bundle, and the
compounding discrepancy corpus. That is exactly a **full-stack developer + ML engineer's** edge.
Plumb needs no proprietary dataset, credential, or model the founder lacks. And it reuses a
proven core: Contig already reproduces and verifies published work in genomics — Plumb lifts
that out of one domain.

---

## Why it's defensible ("gets better as models improve")

The durable core is the pinned re-run + re-derived-vs-reported diff + the accumulated corpus of
labeled discrepancies. A stronger base model extracts **cleaner claims** and writes **better
bindings** — it makes Plumb sharper, never redundant. A judge's guess gets cheaper to fool; a
re-executed number does not.

---

## Positioning

- **Not an AI reviewer.** We do not opine on whether a paper is good, novel, or true.
- **Not a plagiarism / AI-text detector.** Those answer "who wrote this"; Plumb answers "does
  the number hold when you run it."
- **The verdict is honest:** `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`, and
  `UNVERIFIED` is never dressed up as `REPRODUCED`. `DIVERGED` is a reproduction discrepancy
  against the paper's own artifacts, never an accusation of misconduct.

---

## The wedge → the company

1. **OSS on-ramp:** a CLI that takes a paper + its repo and returns a per-claim, reproducible
   verdict with a signed bundle. Free, self-hostable, verifiable. Earn credibility and
   citations; publish a precision/recall benchmark and real, reproducible findings.
2. **Team / community layer:** the discrepancy corpus and benchmark as a shared asset; batch
   verification over a lab's or a field's output.
3. **Hosted layer:** the managed service journals, labs, and authors run submissions through
   (BYOK, opt-in) — the business.

Same playbook as the founder's other projects (Belay, Contig, Whetstone): earn trust with a
free verifiable tool, monetize the managed/enterprise layer later.

---

## Non-goals

- Guessing correctness with a bare LLM judge dressed up as verification.
- Authoring papers, workflows, or analyses (that's someone else's job; we verify the output).
- Accusing anyone of misconduct — we report reproduction discrepancies, verifiably.
- Anything requiring raw-data egress, proprietary datasets, or credentials the founder lacks.
- Any design where a better base model would make Plumb redundant.

---

## The one-line mantra

**Run the paper. Check its numbers against what it actually produced. Prove which ones hold.**
