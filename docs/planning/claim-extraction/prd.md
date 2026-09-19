# PRD — Claim Extraction (C1, deterministic core)

| | |
|---|---|
| Capability | **C1** — `docs/technical/CAPABILITY_ROADMAP.md:17-30` |
| Phase | Phase 0 — Prove the wedge (`docs/ROADMAP.md:15-27`) |
| Branch | `feat/claim-extraction-core/aliz` |
| Depends on | Nothing (`CAPABILITY_ROADMAP.md:29`) |
| Blocks | **C4** (the moat), C7 (no-code path) |
| Status | Drafted, pending review gate |

Sources: `docs/planning/_card/issue.md` (brief), `docs/planning/_card/understanding.md`
(Phase 2 dig). Decisions Q1–Q7 confirmed by the owner in the Phase 3 interview.

---

## Problem Statement

Plumb verifies a paper's quantitative claims by re-deriving them from the paper's own
artifacts and comparing by execution (`VISION.md:8-13`). **You cannot verify what you
have not pinned down** (`CAPABILITY_ROADMAP.md:23`) — every downstream capability
takes a `Claim` as its unit of work. C4 binds a claim to a re-derived value; C5 banks
it; C6 signs it; C7 checks it for internal consistency. None of them can start
without a claim record.

Today no such record exists. The repo is scaffold-only — three commits, no `src/`, no
`pyproject.toml`, no tests.

The evidence this matters is the Phase 0 gate itself: the goal is "what fraction of
headline claims can we bind and re-derive, and how many DIVERGE"
(`ROADMAP.md:17-18`). **That fraction's denominator is C1's output.** An extractor
that under-extracts inflates the coverage number; one that over-extracts buries real
claims in `UNVERIFIED` (R1, `ROADMAP.md:56`). The honest number the whole wedge rests
on is only as trustworthy as claim selection.

## Goals & Success Metrics

**Goal.** A deterministic, offline, test-first extractor that turns a plain-text or
Markdown paper into typed `Claim` records rich enough for C4 to bind without
re-interpreting prose — plus a serialized form stable enough for C6 to bundle.

| Metric | Target | Why |
|---|---|---|
| **Precision / recall on claim *selection*, scored against labels authored before the rule** | Measured and reported on a **blind** fixture set of ~5 real papers; no numeric bar set this slice | Q7 + G1. "Numbers found" is not a metric. Critically, the labels must predate the rule (M15) — otherwise precision/recall measures "the code implements M3", not "M3 is right", and cannot detect a wrong rule. |
| **Determinism** | 100% byte-identical serialized output across repeated runs and across processes | `ARCHITECTURE.md:137`, `:144` |
| **Network calls in test suite** | Zero, enforced by a socket-blocking fixture | `ARCHITECTURE.md:144` |
| **Rejection-list coverage** | Every rejected number category has a failing-first test | Q1 |

Explicitly **not** a goal this slice: a coverage or bind-rate number (that needs C3+C4).

## User Personas & Scenarios

Plumb's ICP — researchers, reviewers, labs, journals — do not interact with C1
directly; it has no user-facing surface in this slice. The consumer is **the engine
itself**, and the human consumer is **the owner**, hand-labeling fixtures to calibrate
selection and reading the claim table to judge whether extraction is honest before
C4 exists to act on it.

A second, load-bearing "persona" is **C4** (`ARCHITECTURE.md:81-101`): it must be able
to write a locator against a `Claim` and detect `AMBIGUOUS_BINDING` without inferring
anything from prose. Requirements below are written to that contract.

## Requirements

### Must-have

**M1. Typed `Claim` record — full width.** Fields: `reported_value` (verbatim text +
`Decimal`), `units`, `metric`/`subject`, `location` (tagged union), `artifact_hint`,
`tolerance_hint` (nullable), stable content-derived `id`.

> **M1 rationale.** `tolerance_hint` is required by `ARCHITECTURE.md:56`. The open
> question at `ARCHITECTURE.md:154` defers tolerance **policy** ("per-claim explicit vs
> a typed default per claim kind"), *not* the existence of the slot — and
> `NO_TOLERANCE` is already a committed `UNVERIFIED` cause (`ARCHITECTURE.md:95-96`),
> so the field has a known consumer. `metric`/`subject` is required because
> `(value, units, span)` is not bindable: C4 aims a locator at a *named quantity*
> (`ARCHITECTURE.md:83-85`).

**M2. `reported_value` is verbatim text + `Decimal`, never float.** Must round-trip
`p < 0.001`, `0.85 ± 0.03`, `95% CI [0.81, 0.89]`, `~10,000`, `12–15%`, and preserve
significant figures (`0.870` ≠ `0.87`).

> **M2 rationale.** `REPRODUCED` requires "matches exactly" (`ARCHITECTURE.md:90`).
> Float coercion turns `p < 0.001` into `0.001` and silently discards precision — a
> false-`DIVERGED` generator, which is **R2: High/High** (`ROADMAP.md:57`).

**M3. Selection rule.** A number is admitted as a claim only if it is (a) asserted by
*this* paper about its own results, (b) carries a named metric, (c) appears in
abstract, results, or a table. Explicit rejection list, each with its own test:
publication/citation years, page/figure/table/equation numbers, version strings,
grant/DOI/ORCID digits, reference-list numerals, hyperparameters, axis labels.

> **M3 rationale.** Guardrail `CLAUDE.md` #3: a related-work number attributed to this
> paper becomes a `DIVERGED` against the wrong authors (**R4**, `ROADMAP.md:59`).

**M4. Ungroundable values surface with a named cause — never silently.** A candidate
that cannot be grounded in the paper text is emitted as a **non-claim record carrying a
cause**, never as a `Claim` and never as a verdict.

> **M4 rationale.** The design docs contradict each other here:
> `CAPABILITY_ROADMAP.md:29-30` says "dropped"; `ROADMAP.md:58` says "`UNVERIFIED` when
> the claim can't be grounded"; `ARCHITECTURE.md:97-98` says "never a silent pass."
> **Resolved in favor of surfacing** (Q2): a silent drop is invisible to the coverage
> number that the Phase 0 gate rests on, and it denies C5's corpus its negative
> examples. *This PRD amends `CAPABILITY_ROADMAP.md:30` — see Follow-ups.*

**M5. The admission gate is the sole constructor of a `Claim`.** Even though the BYOK
proposer is out of scope, no code path may construct a `Claim` except through
deterministic grounding against the paper text.

> **M5 rationale.** Guardrail `CLAUDE.md` #4. If the deterministic core constructs
> records directly, the future proposer gets a second path that bypasses grounding
> (`ARCHITECTURE.md:59-61`). The gate is the part that gets better as models improve;
> the regexes are not.

**M6. Deterministic serialization + paper hash.** A pinned serialized form (JSON with
`sort_keys`, `ensure_ascii`, `separators`, indent and trailing newline all fixed) and a
content hash of the **normalized** paper text, algorithm named explicitly.

> **M6 rationale.** "Byte-identical output" has no referent without a defined
> serialized form, and C6 needs something to bundle (`ARCHITECTURE.md:111-114`). The
> hash must cover the *normalized* text — the same bytes the offsets index — or C6's
> paper hash anchors different content than `location` points at.

**M7. Location as a tagged union**, char offsets over normalized text. Must round-trip
to the exact source span.

**M8. No `confidence` field on `Claim`.** Excluded by construction.

> **M8 rationale.** Guardrail `CLAUDE.md` #1. A confidence float becomes
> `if confidence > 0.9` at verdict time — a model's opinion standing in for a
> re-derived value.

**M9. Determinism controls.** `.gitattributes eol=lf`; no `set` iteration or `hash()`
(`PYTHONHASHSEED` varies per process) — sort by explicit total key; `hashlib` only; no
timestamps or absolute paths in output; Unicode normalized once; documented
overlap-resolution rule for regex alternation (`re` is leftmost-first); single-threaded
as contract.

**M10. Package bootstrap.** `pyproject.toml` via `uv` (committed lockfile,
`--frozen`/`--offline` capable), `src/plumb/extract/` (`ARCHITECTURE.md:53`), pytest
harness with a socket-blocking fixture. Test-first: the failing test precedes the
package (`CLAUDE.md` #7).

**M11. Reported N is extracted as a distinct `StudyParameter` record, not a `Claim`.**
C7 checks statistics against "the reported N" (`CAPABILITY_ROADMAP.md:93`) and depends
on C1 (`:98`), so N must be extracted — but it is not a claim.

> **M11 rationale (G4).** N fails both of M3's admission tests: it carries no named
> metric and is not asserted about the paper's own *results*. It is study metadata. A
> separate record type keeps M3's rule clean and, more importantly, keeps N **out of
> the claim coverage denominator** — no execution "re-derives" a sample size, so
> counting it as a bindable claim would distort the Phase 0 gate number.

**M12. Markdown tables are parsed** — `CAPABILITY_ROADMAP.md:25` places table parsing
in the deterministic core.

**M13. Deduplication by value-identity only.** Locations merge into one claim **only
when the verbatim value string is byte-identical**. Near-duplicates (`0.87` vs
`0.870`) remain separate claims.

> **M13 rationale (G3).** M2 preserves significant figures, so `0.87` and `0.870` are
> different verbatim values — semantic dedup would require a canonical numeric form,
> reintroducing exactly the lossy normalization M2 exists to prevent and seeding R2
> false-`DIVERGED`. Byte-identity keeps the content-derived `id` well-defined (the
> merged claims have identical content) and keeps dedup mechanical and deterministic.
> Cost: a paper that rounds inconsistently is slightly over-counted — visibly and
> honestly, rather than silently merged on a guess.

**M15. Fixture labels precede the rule.** The blind fixture set (~5 real papers, their
headline claims hand-labeled) is committed **before** M3's selection rule is authored,
and M3 is scored against it.

> **M15 rationale (G1).** Without this, the success metric cannot fail: the rule's
> author is also the labeler, so precision/recall measures conformance rather than
> correctness, and the first honest signal on the most consequential decision in C1
> would not arrive until C2+C3+C4 were built on top of it.

**M14. Runtime dependencies are stdlib / pure-parsing only.** No `nltk`/`spacy`-class
packages that download models at import time; no absolute input paths in output.

> **M14 rationale.** Guardrail `CLAUDE.md` #2 (no egress) and the no-network mandate.

### Should-have

- **S1.** `artifact_hint` is paper-internal only (table/figure/section reference), not
  repo-pointing — C2 does not exist yet, so repo-pointing invites speculative guessing.
- **S2.** Record shape kept C7-compatible (`ARCHITECTURE.md:118-122`).
- **S3.** Fixture corpus is synthetic or public-domain (copyright + egress posture).

### Nice-to-have

- **N1.** A `plumb extract` CLI subcommand. *Note: no design doc specifies one —
  `ARCHITECTURE.md:140` defines only `plumb verify`. Out of scope unless trivial.*

## Technical Considerations

- **Pipeline position.** Head of intake → run → re-derive → verdict → bundle
  (`ARCHITECTURE.md:16-44`). Parallel input to C7.
- **Layout.** `src/plumb/extract/` (`ARCHITECTURE.md:53`). Python via `uv`, CLI-first
  (`ARCHITECTURE.md:133`). Test dir and module filenames: docs silent — chosen in
  tech-plan.
- **Determinism & provenance.** "A verdict must be re-derivable from the bundle alone"
  (`ARCHITECTURE.md:137`) pushes the serialization and hashing requirements (M6) into
  this slice rather than C6.
- **Verdict impact: none, by construction.** C1 emits no verdicts. It never renders
  `REPRODUCED`/`WITHIN-TOLERANCE`/`DIVERGED`/`UNVERIFIED`. M5 and M8 are the structural
  guarantees that a model's opinion cannot reach the verdict path
  (`ARCHITECTURE.md:8-10`).

## Risks & Open Questions

| Risk | Ref | Mitigation in this PRD |
|---|---|---|
| **Claim-extraction error** — a number misread or attributed to the wrong paper | **R3** Med/High, `ROADMAP.md:58` | M3 selection rule + rejection tests; M5 admission gate; M4 surfaces failures instead of hiding them |
| **False `DIVERGED`** seeded upstream by lossy value parsing | **R2** High/High, `ROADMAP.md:57` | M2 verbatim + `Decimal`; significant figures preserved |
| **Binding coverage** — claims too thin for C4 to bind | **R1** High/High, `ROADMAP.md:56` | M1 full-width record with `metric`/`subject` and `artifact_hint` |
| **Egress** | **R5** Med/Med, `ROADMAP.md:60` | M14 stdlib-only; no-network test fixture; S3 fixtures |

**Open questions.**
1. **No numeric precision/recall bar is set** this slice. The fixture set is small
   (~5 papers) and labeled by a single person, so early numbers are indicative, not
   defensible — M15 makes them *honest*, not *statistically meaningful*. A defensible
   bar needs C5's corpus and third-party labels.
2. **Selection rule M3 remains provisional** even under M15. Five blind papers can show
   the rule is wrong; they cannot show it is right. Expect revision after the first
   real corpus run.
3. **"Markdown" appears in no design doc** — all three say text/PDF/DOI. This slice
   introduces it as an input mode; `CAPABILITY_ROADMAP.md` should be amended.
4. Tolerance *policy* and locator *grammar* remain open (`ARCHITECTURE.md:154`, `:156`)
   and explicitly do not block C1–C3 (`:158`).
5. **`StudyParameter` (M11) is a new record type named in no design doc.** Its shape is
   deliberately minimal this slice; C7 may require more when it is built.

## Out of Scope

- **PDF → text** and **DOI resolution** (later C1 slices).
- **BYOK LLM proposer** (`ARCHITECTURE.md:59-61`) — the deterministic spine ships
  first, `CLAUDE.md` #4. M5 preserves the seam for it.
- **Tolerance policy** and **locator grammar**.
- Anything in C2–C8: intake, execution, binding, verdicts, corpus, bundle signing.

## ⚠️ Phase 0 accounting

**This slice does not satisfy the Phase 0 C1 minimum.** `ROADMAP.md:21` sets that at
text/**PDF**; this is text/Markdown. A second C1 slice (PDF→text) is required before
the Phase 0 gate can be cleared. C1 must not be marked complete on this slice alone.

## Follow-ups (doc amendments this PRD implies)

1. `CAPABILITY_ROADMAP.md:30` — "dropped" should be reconciled with M4's
   surface-with-cause, and with `ROADMAP.md:58` / `ARCHITECTURE.md:97-98`.
2. `CAPABILITY_ROADMAP.md:19` / `ARCHITECTURE.md:55` — add Markdown as an input mode.
3. `ARCHITECTURE.md:56-57` — record the `metric`/`subject` field and the claim `id`,
   neither of which the current design names.
4. `ARCHITECTURE.md` / `CAPABILITY_ROADMAP.md:93` — record `StudyParameter` as a C1
   output distinct from `Claim`, and note C7 consumes it.

---

## Aspects (decomposition per G2)

Built in order; each has its own `spec.md` and its own `tech-plan` run.

| # | Aspect | Covers | Gates |
|---|---|---|---|
| 1 | [`claim-schema`](claim-schema/spec.md) | M1, M2, M7, M8, M10, M14 | The record every later aspect constructs |
| 2 | [`extraction-core`](extraction-core/spec.md) | M3, M5, M11, M12, M15 | Selection + the admission gate |
| 3 | [`determinism-serialization`](determinism-serialization/spec.md) | M6, M9, M13 | Byte-identity, hashing, dedup |
