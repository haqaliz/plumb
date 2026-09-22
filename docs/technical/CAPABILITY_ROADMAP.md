# Plumb Capability Roadmap (C1..C8)

The engine as a set of capabilities in build order. This is the primary candidate set for
`plumb-next`. Each entry states what it does, why it matters, its dependencies, and its guardrail
tie-in. Phasing lives in [`../ROADMAP.md`](../ROADMAP.md); the design in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

**The moat is C4.** C1–C3 feed it; C5–C6 compound and prove it; C7 extends it to no-code papers;
C8 sells it. Do not let effort drift into anything that a stronger base model would make
redundant (see CLAUDE.md constraint #4).

Verdict vocabulary used throughout: `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` /
`UNVERIFIED`. A model may extract or propose; **execution decides**.

---

## C1. Paper-claim extraction

**What:** take a paper (text, Markdown, PDF, or DOI → text) and produce a set of typed
**quantitative claims** — each with the reported value, units, the metric it measures, location in
the paper, and the artifact it should be derivable from. Reported study parameters (notably N) are
extracted alongside as a **separate record type**, not as claims.

**Why:** you can't verify what you haven't pinned down. The claim is the unit of work.

**Design:** deterministic core (numeric/table/stat parsing) + an **optional BYOK LLM proposer**
that suggests candidate claims. Every LLM-proposed claim is deterministically re-grounded against
the paper text before it is admitted. The proposer never assigns a verdict.

**Depends on:** nothing. **Guardrail:** constraints #1, #3 — a candidate the paper doesn't
actually make never becomes a `Claim`, and is never carried forward as `DIVERGED`. It is recorded
as a **non-claim with a named cause** rather than discarded silently: an invisible drop is
indistinguishable from a claim that was never there, and it flatters the coverage number the
Phase 0 gate rests on (`ARCHITECTURE.md` "never a silent pass"; `ROADMAP.md` R3).

**Status (2026-09-21, seam 2026-09-22):** the deterministic spine of C1 has landed under
`src/plumb/extract/` —
the record layer (`ClaimValue`, `Location`, `Claim`, `StudyParameter`), a content hash over
normalized paper text, byte-identical serialization pinned by cross-process tests, and
value-identity dedup. One pinned runtime dependency — pypdf (pure-Python, no transitive deps),
powering the PDF→Markdown converter in `src/plumb/pdf/`; no network reachable from any test.
The `pdf-input` slice landed test-first through the sealed `extract_claims(raw)` seam
(`src/plumb/extract/pipeline.py:29-61`): claim-id recovery of the PDF path vs the Markdown
path is measured per fixture (`tests/extract/test_pdf_seam.py`). **Four of the five
fixtures clear both recovery floors** (abstract 100%, whole-paper non-table ≥ 0.90, the
survey-set floor) — PMC13134363 19/19 · 19/19 (1.000), PMC13298092 2/2 · 52/54 (0.963),
PMC13363872 9/9 · 9/9 (1.000), PMC13332965 (vacuous abstract) · 38/41 (0.927) — including
the **two-column journals** (the `columns` aspect, 2026-09-22: text-matrix direction,
gutter detection, column grouping, furniture drops). **PMC12780771 (Oxford) remains below
the whole-paper floor** — abstract 6/6, non-table 21/25 (0.840) — and is excluded per PRD
M4 with its measured rate and causes (a pypdf CFF font gap and a sentence broken across a
page break and a table) documented in `fixtures/papers/README.md`: a recorded, labeled
state, never a silent drop.

**Not built:** the whole of C2–C8. **Selection — the substance of this
capability — has landed** (aspect 2 part 2, 2026-09-21): the M3 rule under
`src/plumb/extract/selection.py` with a closed selection-side cause vocabulary, a free-text
metric namer, `extract_claims(raw)` as the end-to-end seam, and pooled precision/recall over
the 73-row blind set — **1.0 / 1.0, floored at 0.90**. The score is a *conformance* score, not
validation: the labels were criteria-drafted from M3/M11 (the owner delegated the pass), so a
perfect score means the rule implements its criteria. Validation against third-party labels is
C5's job. The Phase 0 gate's **C1 prerequisite ("text/PDF") is met for the fixtures as a
whole** — 4/5 fixtures clear the recovery floors, including the two-column journals; the
remaining fixture (PMC12780771, Oxford) is M4-documented with its measured rate (21/25
non-table, 0.840) and named causes. The
gate itself still needs C2–C4, which remain unbuilt, so **the gate is not met and C1 must not
be read as complete.**

## C2. Artifact intake & pinned environment

**What:** resolve the code/data behind the paper — a local path, an `https` git URL with
`--rev`, an archive — into a **pinned checkout** (tree hash recorded) and build a reproducible
environment on the **user's compute**.

**Why:** reproducibility is impossible without a pinned, rebuildable environment.

**Depends on:** nothing. **Guardrail:** constraint #2 — everything stays local; nothing is
fetched to a third party the user didn't authorize.

## C3. Execution & result capture

**What:** run the repo's own entry point(s) and capture structured outputs — JSON, CSV, stdout,
notebook cell outputs — **content-addressed** and **freshness-guarded** (an output file whose
mtime/provenance predates this run is never read as a fresh result).

**Why:** the re-derived value must come from an actual run, not a committed artifact.

**Depends on:** C2. **Guardrail:** constraint #5 — reproduce what ran, not what was committed.

## C4. Claim↔artifact binding & re-derivation verdict — **the moat**

**What:** bind each C1 claim to a value re-derived in C3 via a **locator** (JSON pointer, table
cell reference, regex/stdout capture, notebook cell), compare within a stated tolerance, and emit
the per-claim verdict: `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`.

**Why:** this is the product. Everything else exists to make this verdict trustworthy.

**Design:** a model may *propose* a binding; the comparison and verdict are done by code. Any
failure to bind, run, or set a tolerance resolves to `UNVERIFIED` with a named cause. `DIVERGED`
requires the artifact's own run to contradict its own claim.

**Depends on:** C1 + C3. **Guardrail:** constraints #1, #3 — never `REPRODUCED` on a model's
say-so, never `DIVERGED` on a harness-side failure.

## C5. Discrepancy corpus & calibration benchmark

**What:** accumulate every (claim, re-derived value, verdict, locator, cause) into a labeled
corpus; publish a precision/recall benchmark over a public paper corpus.

**Why:** the compounding moat and the credibility instrument. Precision on `DIVERGED` is the
number the whole reputation rests on.

**Depends on:** C4. **Guardrail:** constraint #4 — the corpus is the asset that a better base
model cannot hand you for free.

## C6. Signed, replayable reproduction bundle

**What:** a signed record binding paper hash + repo tree hash + environment + run traces +
per-claim verdicts, such that a third party can **replay** and reach the same verdicts.

**Why:** a finding nobody can independently replay is an opinion. This makes `DIVERGED`
defensible and `REPRODUCED` auditable.

**Depends on:** C4. **Guardrail:** constraints #2, #3 — only what the user chooses to publish is
in the bundle; the bundle is the evidence, not an accusation.

## C7. Internal-consistency checks (no-code path)

**What:** for PDF-only papers with no runnable artifacts, run statcheck/GRIM-style
internal-consistency checks (do the reported statistics agree with each other and the reported N).

**Why:** extends coverage to the majority of papers that ship no code — but as a **weaker,
clearly labeled** signal.

**Depends on:** C1 — specifically on C1's `StudyParameter` records, which carry the reported N
these checks are run against. N is deliberately *not* a `Claim`: no execution re-derives a sample
size, so counting it as one would distort the bind-and-re-derive coverage number.
**Guardrail:** constraint #3 — an internal inconsistency is labeled as such, never rendered as a
ground-truth `DIVERGED` from re-execution.

## C8. Hosted layer (BYOK, opt-in) — the business

**What:** a managed service journals, labs, and authors run submissions through, with the OSS
engine underneath. BYOK, opt-in, runs on infrastructure the customer authorizes.

**Why:** the revenue layer, on the usual OSS-on-ramp → managed-layer playbook.

**Depends on:** C4 + C5 + C6. **Guardrail:** constraint #2 — no raw-data egress the customer
didn't authorize; verdicts and bundles, not datasets.

---

## Sequencing summary

| Order | Capability | Rationale | Depends on |
|---|---|---|---|
| 1 | C1 Claim extraction | Defines the unit of work | — |
| 2 | C2 Artifact intake & pinned env | Reproducibility precondition | — |
| 3 | C3 Execution & result capture | Produces the re-derived value | C2 |
| 4 | **C4 Binding & verdict** | **The moat** | C1, C3 |
| 5 | C5 Discrepancy corpus & benchmark | Compounds + proves precision | C4 |
| 6 | C6 Signed replayable bundle | Makes findings defensible | C4 |
| 7 | C7 No-code consistency checks | Extends coverage (weaker signal) | C1 |
| 8 | C8 Hosted layer | The business | C4, C5, C6 |

**One-line mantra:** run the paper, check its numbers against what it actually produced, prove
which ones hold.
