# PRD — discrepancy-corpus (C5, first slice)

- **Capability:** C5 — Discrepancy corpus & calibration benchmark (`docs/technical/CAPABILITY_ROADMAP.md:209-218`).
- **Source:** `docs/planning/_card/issue.md` (pbf handoff brief, 2026-10-01); understanding note: `docs/planning/discrepancy-corpus/understanding.md`.
- **Date:** 2026-10-01. **Owner:** aliz.

## Problem Statement

The Phase 0 gate is met on one paper (`docs/ROADMAP.md:29-33`), but **cross-paper binding
coverage (R1, High/High) is still unmeasured** (`docs/ROADMAP.md:32-33, 68`) — there is no
instrument that turns every verify run into an accumulating, labeled record of
(claim, re-derived value, verdict, locator, cause). Without it, precision on `DIVERGED` —
"the number the whole reputation rests on" (`CAPABILITY_ROADMAP.md:214-215`) — is
uncomputable, R2's false-`DIVERGED` bar has no measured false-positive rate, and the
compounding moat ("the asset that a better base model cannot hand you for free",
`CAPABILITY_ROADMAP.md:217-218`) never accrues. C5 is moat #2 (`docs/technical/ARCHITECTURE.md:148-154`)
and the calibration instrument for the R1/R2 pair.

## Goals & Success Metrics

1. **Bank every verdict run** as a self-contained, replayable, human-labelable case under
   gitignored `corpus/local/` (`ARCHITECTURE.md:150-151`), byte-identical canonical
   serialization (the house determinism contract: sorted keys, Decimals as text, no floats,
   cross-process identity — `docs/planning/binding-verdict/prd.md:39-41, 169-171`).
2. **Case #1 without re-running:** the committed AgroDesign record
   (`fixtures/gate/agrodesign/`) folds in via `plumb corpus bank` (86 claims, 85
   `REPRODUCED`, 1 `DIVERGED`, 0 `UNVERIFIED`, 2 non-claims — `fixtures/gate/agrodesign/README.md:55-63`).
3. **Benchmark scaffold** computes per-claim precision/recall/coverage against **human
   labels**; `UNVERIFIED` excluded from precision; engine never labels its own cases
   (`ARCHITECTURE.md:152-154`).
4. **The R1 measurement exists:** the bank's coverage report is the first honest
   cross-paper coverage number, ugly or not (`_card/issue.md:14-16`).

**Success metrics (this slice):** AgroDesign banks byte-identically (round-trip equality);
the banked case re-derives its own 86 verdicts from its stored trace alone, matching
`verdicts.json` exactly; coverage/precision math excludes `UNVERIFIED` (proven by test, not
prose); no banked case is ever mutated (append-only); full suite stays network-free. **Every
benchmark figure carries its denominator and a label-authority marker** (owner vs
third-party) — a precision number over a single owner-confirmed `DIVERGED` is reported as
such, never as a validated rate.

## User Personas & Scenarios

- **Owner/aliz** — runs `plumb verify` on real papers, then `plumb corpus bank <record-dir>`
  to fold each run into the local corpus; reads the coverage report to answer "what fraction
  of claims bind and re-derive across papers?" (R1).
- **Third-party verifier (future)** — replays a banked case from its own stored bytes
  (self-contained by construction) and reaches the same verdicts; labels cases independently,
  the validation source for C1's conformance scores (`CAPABILITY_ROADMAP.md:63-66`).

## Requirements

### Must-have

- **R1 — Corpus store (`src/plumb/corpus/`).** A `bank_case(...)` library seam that writes
  one case per verify run: `case.json` (case manifest: case_id, paper hash, run_id, member
  hashes), `claims.json`, `bindings.json`, `trace.json`, `objects/`, `verdicts.json`,
  `nonclaims.json` (when present), under gitignored `corpus/local/` (`.gitignore:20`).
  Canonical serialization reusing the existing contracts (`serialize_verdicts`,
  `serialize_trace`, the `_JSON` options triplet) — never a re-spelling.
- **R2 — Content-addressed case identity.** `case_id` = SHA-256 over the case's serialized
  members (paper hash + run_id + claims/bindings/trace/verdicts hashes — same derivation
  style as `derive_run_id`, `src/plumb/run/trace.py:69-75`). Re-banking an identical record
  is a **no-op** (append-only store); the store **never mutates an existing case**
  (`_card/issue.md:19`). The case manifest records every member's SHA-256: a re-bank whose
  `case_id` matches an existing case but whose member bytes differ (tamper, or a different
  record hashing identically) is **refused with a named cause**, never merged, never
  overwritten.
- **R3 — Bank command.** `plumb corpus bank <record-dir> [--store DIR]` (new `corpus`
  subcommand — verify-cli explicitly left C5 writes out, `docs/planning/verify-cli/prd.md:180`):
  reads the record directory (`claims.json + bindings.json + trace.json + objects/ +
  verdicts.json`, the shape already proven by `src/plumb/cli/replay.py:96-124`), validates it
  (`parse_trace` run-id check), **re-derives the verdicts from the stored trace** (the replay
  chain: `parse_trace` + `Capture(store=objects, …)` rebuild + `verify_claims`,
  `src/plumb/cli/replay.py:118-121`), refuses to bank on any mismatch, and writes the case.
  Folding AgroDesign in is the acceptance run.
- **R4 — Non-claim lane.** The case carries non-claims with their named causes (AgroDesign's
  `unrepresentable.json`: 2× "p ¡ 0.001"). R3's never-silent-drop rule:
  `docs/planning/claim-extraction/prd.md:96-105` — the corpus's negative examples. Non-claims
  count in coverage denominators but **never** in verdict precision.
- **R5 — Benchmark scaffold.** Given a store + human labels, compute per-claim
  precision/recall/coverage: coverage = bound/claims (the C4 bound definition,
  `docs/planning/binding-verdict/prd.md:179-181`); **precision on `DIVERGED`** =
  confirmed-`DIVERGED` / (confirmed + refuted `DIVERGED`s); recall =
  confirmed-`DIVERGED` / human-flagged problems; `UNVERIFIED` excluded from precision
  (`ARCHITECTURE.md:152-154`); an unlabeled `DIVERGED` is never counted as confirmed (it
  lands in neither numerator nor denominator); canonical JSON output (byte-identical).
  **Every figure reports its denominator and a label-authority marker** (`owner` /
  `third-party`): precision over a single owner-confirmed `DIVERGED` is rendered as `1/1
  (owner-labeled)`, never as a bare rate that reads as validation.
- **R6 — Labels.** Per-claim `labels.json` beside the case — canonical JSON object keyed by
  `claim_id`, values `"confirmed"` or `"refuted"` (absent = `unlabeled`), sorted keys,
  Decimals-as-text house rules; **human-written, engine-read** — the engine never decides a
  label value ("engine never labels its own cases", `ARCHITECTURE.md:154`). The bank
  command **transports, never creates, labels**: it copies a human-authored review into the
  case (case #1's `DIVERGED` ships pre-labeled `confirmed`, sourced from the owner's
  committed review, `fixtures/gate/agrodesign/README.md:75-82`) and writes no `labels.json`
  at all when nothing human-authored exists. States: `unlabeled` / `confirmed` / `refuted`.

### Should-have

- **S1 — Determinism tests in the house style:** cross-process `PYTHONHASHSEED` byte
  identity for the case manifest and the coverage report (the
  `tests/extract/test_determinism.py:320-366` harness pattern), closed-schema pinning,
  vacuity controls.
- **S2 — `--store` default.** `corpus/local/` at the repo root (gitignored) as the default
  store path, overridable.
- **S3 — Report surface.** `plumb corpus report [--store DIR]` renders the coverage/precision
  summary (table or canonical JSON) from a store; honest when the first numbers are ugly.

### Nice-to-have

- **N1 — Store-wide index** (`index.json`: case ids, counts, label totals) regenerated
  deterministically.
- **N2 — `plumb verify --bank`** fold-in so live runs bank automatically.

## Technical Considerations

- **Capability:** C5, depends on C4 only (`CAPABILITY_ROADMAP.md:218`) — C4 is built
  (`src/plumb/verify/`, incl. value-kinds compare; the roadmap prose at
  `CAPABILITY_ROADMAP.md:194` is stale — code runs ahead of docs). This slice introduces no
  new dependency; no network in any test (`tests/conftest.py:56-60` autouse blocker).
- **Reuse, don't re-invent:** the record directory *is* the case shape
  (`replay.py:96-124`); the replay chain is the re-derivation guarantee
  (`replay.py:118-121`); `serialize_verdicts` (`verify/serialize.py:40-47`) and
  `parse_trace` (`run/trace.py:134-180`, which recomputes and validates the run id) are the
  canonical bytes contracts. `corpus/local/` is already gitignored.
- **Determinism:** every new serialized artifact (case manifest, labels, coverage report)
  follows the house rules — sorted keys, no incidental whitespace, `Decimal` as exact text,
  no floats, no timestamps/absolute paths in the bytes, one trailing newline.
- **Verdict impact — none.** This slice never changes what a verdict claims. Execution
  still assigns every verdict (`verify_claims`); the corpus only *banks* the evidence chain
  the verdict already carries (`claim_id, reported_text, located_text, sha256, run_id,
  rederived, band/delta, locator, cause, review_required` — `verify/verdict.py:49-113`).
  Labels are human and external; the engine never suggests them (precedent:
  `docs/planning/claim-selection/prd.md:195`).
- **Freshness/provenance:** a banked case carries the run's captured bytes by SHA-256
  (`objects/`), never re-read committed outputs as fresh results (constraint #5,
  `CLAUDE.md`); `STALE_ARTIFACT` records remain verdict evidence, never fresh reads.
- **No egress:** `corpus/local/` is user-run-state ("never leave the box",
  `.claude/skills/plumb-worktrees/SKILL.md:85-87`; R5, `ROADMAP.md:72`). Export for a public
  benchmark is a later, user-chosen slice.

## Risks & Open Questions

- **R1 (High/High) — the honest number may be ugly.** The first real coverage number comes
  from a record with 0 `UNVERIFIED` (AgroDesign); the exclusion math is exercised
  synthetically until a real UNVERIFIED-heavy paper banks. The scaffold must report
  coverage without flattering it (`_card/issue.md:15`). Open: none — the report's
  honesty is a success criterion.
- **R2 (High/High) — precision-on-`DIVERGED` is only as good as the C4 chain.** Every
  banked `DIVERGED` carries `review_required` (D5, `binding-verdict/prd.md:93-95`) and the
  AgroDesign one is drift-cross-checked (`drift.json`, `gate-paper/prd.md:92-96`). The
  benchmark's precision math must never count an unlabeled `DIVERGED` as confirmed.
  Open: how labels migrate from "beside the case" (README:80-82) to the store — resolved
  by R6 (labels.json beside the case).
- **R3 (Med/High) — extraction errors.** Non-claims are banked with named causes (R4);
  the bank's re-admission check (`parse_claims`-style) must not admit a non-claim as a
  claim. Open: whether banking re-admits curated claims through the admission gate (the
  replay precedent does — `replay.py:127-169`); default yes, flag if it bites.
- **Open — benchmark denominators for non-claims:** decided (per-claim, DIVERGED-precision;
  non-claims in coverage denominators only).
- **Open — label authorship:** owner labels case #1's DIVERGED at bank time (R6). No
  third-party label flow in this slice.

## Out of Scope

- Public benchmark publication, corpus export, or any data leaving the box (R5).
- Labeling UI / third-party labeling workflow beyond the labels.json schema.
- Notebook-cell capture and locators; C7 (no-code consistency); C6 follow-ons (bundle CLI,
  tar, sigstore); the binding proposer.
- Banking from live `plumb verify` runs is N2 (nice-to-have), not required.

## Acceptance Tests (written first — the repo is test-first)

1. Banking the committed AgroDesign record (`fixtures/gate/agrodesign/`) writes a case that
   round-trips **byte-identically** (bank → read → re-serialize == the record's own bytes).
2. A banked case **re-derives its verdicts from its own stored trace** (parse_trace +
   Capture rebuild + verify_claims) matching the banked `verdicts.json` exactly (85
   `REPRODUCED`, 1 `DIVERGED`, 0 `UNVERIFIED`).
3. Re-banking the identical record is a **no-op**; the store **never mutates** an existing
   case (tamper test: modified member → refused with a named cause, not overwritten).
4. Benchmark math: `UNVERIFIED` excluded from precision (synthetic case with a mix of
   verdicts); unlabeled `DIVERGED` never counted as confirmed; per-claim denominators;
   canonical JSON output byte-identical across processes/seeds.
5. Non-claims bank with their named causes and never count in verdict precision.
6. Case #1 ships with its DIVERGED pre-labeled `confirmed` (the owner's committed review
   transported by the bank, never created by it — an unlabeled run banks with **no**
   `labels.json` at all, and a guard-mutation check proves the engine never invents a label
   value).
7. No network: the suite passes under the autouse blocker (`tests/conftest.py:56-60`).