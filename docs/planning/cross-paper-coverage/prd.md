# PRD — cross-paper-coverage (C5, next slice)

- **Capability:** C5 — Discrepancy corpus & calibration benchmark (`docs/technical/CAPABILITY_ROADMAP.md:209-218`).
- **Source:** `docs/planning/_card/issue.md` (pbf handoff brief, 2026-10-02); understanding note: `docs/planning/cross-paper-coverage/understanding.md`.
- **Date:** 2026-10-02. **Owner:** aliz.

## Problem Statement

R1 — cross-paper binding coverage (High/High) — is the last unmeasured risk
(`docs/ROADMAP.md:68`): "most repos don't run, or never expose the headline number in a
machine-readable place". Phase 1's remaining work is headed by "harden against real repos
(R1 — cross-paper coverage is still unmeasured)" (`docs/ROADMAP.md:41-45`). The corpus
instrument shipped 2026-10-01 (PR #12: store, bank, labels, metrics, report — C5's first
slice), but it holds exactly one case, and nothing feeds it: **the live spine writes no
record dir** — `--out` writes only the signed bundle (`src/plumb/cli/live.py:154-157`), and
the only record writer in the repo is dev-time `tools/gate_run.py:118-124`. The verify→bank
loop is open; the compounding moat ("the asset that a better base model cannot hand you for
free", `CAPABILITY_ROADMAP.md:217-218`) has nothing to compound; precision on `DIVERGED` —
"the number the whole reputation rests on" (`CAPABILITY_ROADMAP.md:214-215`) — remains a
1/1 owner-labeled figure over one paper.

## Goals & Success Metrics

1. **Close the verify→bank loop:** `plumb verify --bank` persists a run's record dir and
   banks it through the existing corpus replay chain — the N2 fold-in the corpus PRD named
   (`docs/planning/discrepancy-corpus/prd.md:113-114`). `--from-record --bank` banks a
   record already in hand.
2. **Run a real panel:** 3–5 runnable Python/R data-analysis papers, selected by a
   **fixed, pre-written rule** (anti-inflation; the `survey.md:6-14` criteria + the
   gate-paper PRD's P2 guard, `docs/planning/gate-paper/prd.md:37-45`), each with a
   committed fixture, a committed record, and a banked case — the first multi-paper code
   fixtures (`fixtures/gate/` holds only agrodesign today).
3. **The R1 measurement exists:** `plumb corpus report` pools the panel with per-case and
   pooled denominators and label-authority markers; R1's status in `docs/ROADMAP.md` is
   updated with the honest number, ugly or not (`UNVERIFIED` is the honest default).
4. **Per-paper C1 recovery measured and reported as conformance**, never extraction
   coverage (`CAPABILITY_ROADMAP.md:85-87`).

**Success metrics (this slice):** a live run with `--bank` writes a record that re-derives
byte-identically and banks (re-bank is a no-op, append-only); the banked case contains no
stderr / local paths; a second paper's committed record banks and re-derives from its
stored trace matching its `verdicts.json`; the report pools ≥ 2 cases with denominators and
`authority` markers; the suite stays network-free (`tests/conftest.py:56-60`); real env
builds run only at dev time via `tools/` (`tools/demo_env_build.py:1-16` precedent).

## User Personas & Scenarios

- **Owner/aliz** — runs `plumb verify <paper> <repo> --bindings ... --bank` on real papers;
  each run lands in the corpus without hand-assembly; reads `plumb corpus report` to answer
  "what fraction of claims bind and re-derive across papers?" (R1).
- **Third-party verifier (future)** — replays a banked case from its own stored bytes and
  reaches the same verdicts; labels cases independently (the validation source for C1's
  conformance scores). The panel's owner-reviewed `DIVERGED`s are the first candidates for
  that lane.

## Requirements

### Must-have

- **R1 — Record writer for live runs.** A `src/plumb` function (new, in `cli/` or
  `corpus/`) assembles the record dir from what `_spine` already holds after
  `verify_claims` (`src/plumb/cli/live.py:153`): `claims.json` in the **C1 record form**
  (`serialize_claims`, `extract/serialize.py:300-348`, including `paper_hash`),
  `bindings.json` (the raw bytes already read, `live.py:130`), `trace.json`
  (`serialize_trace`), `objects/` — **locatable outputs only, stderr excluded**
  (`capture.locatable`; `tools/gate_run.py:122-123` precedent — the live capture store
  contains stderr, `capture.py:109-112`, and `bank_case` copies every file, `store.py:205-217`),
  `paper.pdf|md` (the bytes already read, `live.py:128`), `verdicts.json`
  (`serialize_verdicts`). Written to a temp/scratch area, never the pinned checkout.
- **R2 — Dual-form claims read.** `read_record` (`src/plumb/cli/replay.py:96-124`) learns
  to accept the C1 record form: detect by shape (`paper_hash` present), read through
  `parse_claims` + the admission gate with the record's own paper — the exact read the
  bundle path already proves (`src/plumb/bundle/verify.py:185-191`) — and verify the
  paper hash against the record's paper bytes. The curated six-field form
  (`replay.py:63, 152`) is unchanged; existing AgroDesign tests must not move.
- **R3 — `--bank` flag.** On `plumb verify`, valid in both live and `--from-record` modes:
  banks into the default store (`corpus/local/`) through the existing `bank_record`
  replay chain (`src/plumb/cli/corpus.py:87-106` — "a record that would not replay does
  not bank"), write-once/no-op semantics from `bank_case` (`corpus/store.py:87-92`).
  Verdicts render regardless; a bank refusal is the named cause `CORPUS_REFUSED`
  (`cli/__init__.py:370`), exit 1; `--bank` prints the case id. The record is discarded
  after banking — the case is the durable artifact. **A failed or stubbed run banks
  too:** a `WONT_RUN` / `NO_ARTIFACT` / `TIMEOUT` run or a `--no-env-build` stub produces
  an all-`UNVERIFIED` case with its named causes in the trace — the honest default, not a
  refusal (pinned by test: such a case banks with its run-level cause intact and
  `UNVERIFIED` verdicts).
- **R4 — The panel.** A **fixed selection rule written before any paper is chosen**
  (openly licensed paper text; public pure-Python/R code; laptop-CPU minutes; no run-time
  network; data bundled or generated; headline numbers printed/written as JSON/CSV;
  deterministic or seeded — `docs/planning/gate-paper/survey.md:6-14`). A screening note
  records candidates and why each did or didn't qualify (the `survey.md:23-54` pattern;
  ReScience was already exhausted). Panel target: 4 papers. **Floor: 2 banked cases
  (AgroDesign + one new paper) is the first shipped milestone — the pooled report is
  valid at 2 and the denominators make the panel size visible either way. If screening
  finds fewer than 2 qualifying papers after a documented wider search (arXiv), the
  finding is the number itself: the survey becomes the R1 evidence, reported with zero
  padding.** Papers whose repos fail to run at dev time are reported as selection misses,
  not forced through.
- **R4b — Milestone sequencing.** Milestone 1 = the `--bank` slice (R1–R3) + the first
  new paper end-to-end (fixture, record, bank, tests) — the report then pools 2 cases.
  Milestone 2 = panel growth to target with per-paper records; each paper lands as its
  own committed unit, in dependency order of nothing (independent), so a paper that
  stalls never blocks the rest.
- **R5 — Per-paper fixture, record, bank.** For each panel paper, following the
  AgroDesign template: provenance README with SHA-256 pinning
  (`fixtures/gate/agrodesign/README.md:6-16`); a spec generator in the
  `tools/agrodesign_spec.py` shape (rule-encoded data tables; spans **found** via
  exactly-once context search, never typed; claims + bindings + `unrepresentable.json`
  derived together); a dev-time run (`tools/gate_run.py` shape: `resolve_git` at a pinned
  rev, real env build + freeze, run in a working copy, locatable-only objects); the
  committed record; `plumb corpus bank` the case; C1 recovery measured per paper
  (place+value) and reported.
- **R6 — The honest number.** `plumb corpus report` over the panel; per-case rows and
  pooled totals, every figure with its denominator and label-authority marker; every
  `DIVERGED` owner-reviewed (`review_required`, labels transported not created,
  `corpus.py:12-17`) before it counts in precision. R1's status in `docs/ROADMAP.md`
  updated; per-paper C1 recovery framed as conformance.

### Should-have

- **S1 — M4a drift cross-check + signed bundle where a `DIVERGED` appears.** The
  older-environment re-run and `drift.json` (`docs/planning/gate-paper/prd.md:92-96`; a
  verdict that changes → `UNVERIFIED`, never `DIVERGED`) and a signed bundle
  (`tools/bundle_build.py` pattern) for every paper with a `DIVERGED`; clean
  `REPRODUCED` panels skip both.
- **S2 — Panel tooling.** One dev-time script (or per-paper scripts in the
  `tools/gate_run.py` shape) that runs a paper's workflow and writes the record, so the
  campaign is repeatable, not one-off shell history.
- **S3 — Recovery floor tests per fixture.** Where a paper's measured recovery clears it
  (the AgroDesign floor pattern, `tests/gate/test_agrodesign_recovery.py:30-31`), pin the
  floor; where it doesn't, the number is reported and the gap documented.

### Nice-to-have

- **N1 — Live records `--out`-ready.** The writer also emits `environment.txt` and
  `source.json` (the six `SourceRecord` fields, `replay.py:65-67`) so a live-written
  record also supports `--from-record --out` bundle rebuilds. `SourceRecord` has no
  serializer today — a small mapping.
- **N2 — Nonclaims lane on live runs.** C1 rejections (`extract_claims`' second return,
  `extract/pipeline.py:44-59`) written as `nonclaims.json` when present, feeding coverage
  denominators without touching verdict precision. Lane is optional in the case format
  (`corpus/case.py:54`).

## Technical Considerations

- **Capability:** C5, depends on C4 only (`CAPABILITY_ROADMAP.md:218`) — built
  (`src/plumb/verify/`). The bank/replay machinery this slice builds on is built
  (`src/plumb/corpus/`, `src/plumb/cli/corpus.py`, `replay.py`).
- **Reuse, don't re-invent:** the replay chain is the validation
  (`corpus.py:87-106`); `bank_case` supplies write-once semantics; `serialize_claims` /
  `serialize_trace` / `serialize_verdicts` are the canonical bytes contracts; the dual-form
  read reuses the bundle's `parse_claims` + admission-gate read
  (`bundle/verify.py:185-191`); the campaign reuses the `agrodesign_spec.py` /
  `gate_run.py` shapes.
- **The claims-form decision is load-bearing.** Live claims are C1 `Claim` objects with no
  `source`/`context` (`live.py:129`); the curated form demands them (`replay.py:63, 152`).
  Writing the C1 form and teaching `read_record` to accept it avoids inventing
  provenance fields; the shape probe must be unambiguous (test both forms).
- **Determinism:** every new serialized artifact follows the house rules — sorted keys, no
  incidental whitespace, `Decimal` as exact text, no floats, no timestamps/absolute paths,
  one trailing newline. A live-written record must replay byte-identically through
  `read_record` → `verify_claims` → `cross_check`.
- **Verdict impact — none.** Banking never changes what a verdict claims; labels are human
  and external; the engine never suggests them.
- **Freshness/provenance:** only `capture.locatable` leaves the run area; stderr (which
  may carry local paths) never enters the record, the case, or the bundle.
- **No egress:** paper runs and env builds happen on the user's compute at dev time
  (`tools/` precedent); tests stay network-free (`tests/conftest.py:56-60`); the corpus
  store stays gitignored (`/corpus/local/`, `.gitignore:15-20`).

## Risks & Open Questions

- **R1 (High/High) — the honest number may be ugly.** Most repos don't run or never expose
  the headline number machine-readably; the screening survey already predicts the failure
  mechanisms (figures-only results, notebook-computed tables, unseeded stochastic
  aggregates — `survey.md:40-54`). The panel rule narrows to runnable papers (the R1
  mitigation, `ROADMAP.md:68`); a repo that fails at dev time is a documented selection
  miss. The report must not flatter; coverage with `UNVERIFIED` causes is the expected
  early shape. Open: panel size final call (3 minimum for a pooled figure; target 4).
- **R2 (High/High) — precision-on-`DIVERGED` only as good as the C4 chain + review.** Every
  banked `DIVERGED` carries `review_required` and needs the M4a drift cross-check (S1) and
  an owner review before it counts as `confirmed` in precision; an unlabeled `DIVERGED`
  lands in neither numerator nor denominator.
- **R3 (Med/High) — claim-extraction error on new papers.** C1 recovery is unmeasured
  beyond AgroDesign; expect per-paper tuning (the `claim-recovery` precedent,
  `CAPABILITY_ROADMAP.md:76-87`). Recovery is measured and reported as conformance; a
  paper whose curated claims C1 cannot recover is a finding, not a silent retune.
- **Dual-form read risk.** A shape probe that misdetects would either refuse valid records
  or silently admit the wrong form; pinned by tests over both forms plus a tamper case.
- **Objects hygiene.** `bank_case` copies every `objects/` file (`store.py:205-217`);
  shipping stderr would break the no-local-path invariant — the writer must copy only
  `capture.locatable`, pinned by test.
- **Open — live nonclaims.** Whether C1 rejections bank as `nonclaims.json` (N2) or the
  lane stays fixture-only for this slice; default: fixture-only, revisit when a live run
  shows real non-claims worth banking.
- **Open — the two record forms.** Live records carry the C1 form (this PRD); gate
  fixtures carry the curated six-field form. Both are read by `read_record` after R2.
  Whether the curated form is a permanent format or a gate-fixture artifact to migrate to
  the C1 form later is a follow-on decision, not this slice — but the dual-form reader is
  designed so the curated branch can be retired without touching the C1 branch.

## Out of Scope

- The C4 binding proposer; C7 (no-code consistency); C6 follow-ons (bundle CLI, tar,
  sigstore, timestamps); C8.
- `--timeout-seconds` / `--run-dir` knobs (`ROADMAP.md:44-45`); notebook-cell capture and
  locators; a `--store` override on `--bank` (flag-only, default `corpus/local/`).
- Public benchmark publication / corpus export — nothing leaves the box (R5).
- Labeling UI / third-party labeling workflow; the binding proposer's reserved causes stay
  reserved.

## Acceptance Tests (written first — the repo is test-first)

1. A synthetic live run with `--bank` writes a record that re-derives byte-identically and
   banks; the banked case's `objects/` contain locatable outputs only (no stderr, no local
   paths); re-bank is a no-op; a conflicting re-bank is `CORPUS_REFUSED`.
2. A live-written C1-form record replays through `read_record` byte-identically
   (`--from-record --json` == its `verdicts.json`); the curated-form AgroDesign record
   replays unchanged (existing tests do not move); a tampered C1-form record is refused.
3. `--from-record --bank` on the AgroDesign record reports already-banked (no-op), exit 0.
4. A second paper's committed record banks and re-derives from its stored trace matching
   its `verdicts.json`; its fixture tests (grounding, PDF hash, no local paths) pass.
5. `plumb corpus report` pools ≥ 2 cases with per-case and pooled denominators and
   label-authority markers; `--json` byte-identical across invocations and
   `PYTHONHASHSEED` values.
6. Every panel paper's C1 recovery is measured and reported; R1's status in
   `docs/ROADMAP.md` is updated with the honest number and its denominators.
7. No network: the suite passes under the autouse blocker (`tests/conftest.py:56-60`);
   real env builds run only via `tools/` at dev time, never in tests or CI.