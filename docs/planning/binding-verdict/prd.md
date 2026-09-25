# PRD — C4 binding & verdict, first slice (`binding-verdict`)

Source: `docs/planning/_card/issue.md` (inline brief from `plumb-next`) and
`docs/planning/_card/understanding.md` (deep dig). Decisions D1–D6 below were put to the owner
as recommendations and accepted as a set on 2026-09-25 ("sure"); D4 takes the safer of the two
offered variants. D7–D8 came out of the self-critique and were approved at the review gate.

**Status (2026-09-25): landed** on `feat/binding-verdict/aliz` — all three aspects
(`locators`, `compare`, `verdict-seam`), 1395 tests passing offline. One amendment during the
build: D7's coarse-artifact check was first implemented *after* the band check, which made a
run's `0.9` against a paper's `0.90` a false `REPRODUCED`; it now runs first, as D7 states
(`compare/spec.md` criterion 12). Verdicts exist on synthetic repos only; the Phase 0 gate is
not met.

## Problem Statement

Plumb has never emitted a verdict. C1 turns a paper into `Claim` records, C3 turns a repo into
a `RunTrace` plus a content-addressed `Capture`, and nothing joins them. Until something does,
the Phase 0 gate — "bind one headline claim to a re-derived value and emit the verdict"
(`docs/ROADMAP.md`) — cannot be attempted, and C5 (corpus), C6 (bundle) and C8 (hosted) are all
blocked (`docs/technical/CAPABILITY_ROADMAP.md`, sequencing table).

This is C4, the moat, and it is where risks **R1** (binding coverage) and **R2** (false
`DIVERGED`) — both High/High — are either mitigated in code or not at all. The slice's job is
to make the verdict *honest* first and *broad* later: every claim gets exactly one verdict,
every `UNVERIFIED` has a named cause, and `DIVERGED` is structurally unreachable on a
harness-side failure.

## Goals & Success Metrics

- **G1 — The verdict exists.** `verify_claims(claims, bindings, run)` returns one verdict
  record per input claim — none dropped, none duplicated — and a coverage summary (claims in,
  bound, per-verdict counts, per-cause counts). That summary is the shape of "the number" the
  Phase 0 gate rests on.
- **G2 — No false `DIVERGED` from the harness.** Every C3 failure cause and every C4
  binding-side failure resolves to `UNVERIFIED` with its cause. Pinned by a load-bearing test
  with a mutation check: weakening the run-failure precedence or the fresh-artifact requirement
  fails the suite.
- **G3 — Determinism.** Verdict records serialize to canonical bytes, byte-identical across
  processes, with `Decimal`s as verbatim text (the `plumb.extract.serialize` / `run.trace`
  contract).
- **G4 — Offline.** The whole suite runs with no network. End-to-end tests use synthetic local
  repos run through C3's real `run_and_capture` (the C3 test pattern).

Metric for the slice is conformance, not coverage: every acceptance criterion below is a
failing test first. Real-paper coverage is the gate paper's job (out of scope, see Risks).

## User Personas & Scenarios

- **A reviewer or reproducibility lab** has a paper, its repo, and a run. They write a small
  bindings file saying "claim X is `results.json` at `/metrics/auc`" and get back, per claim,
  `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED: <cause>`, with the located
  value, the band or tolerance that decided it, and the artifact hash it came from.
- **The founder, running the Phase 0 gate**, needs the coverage summary to report how many
  headline claims bound and how many diverged, without any `UNVERIFIED` being hidden inside a
  pass rate.

## Decisions (owner-accepted, 2026-09-25)

- **D1 — Written precision is part of the claim.** A `Point`'s *precision band* is ± half a
  unit in the last digit the paper wrote, read from the parsed `Decimal`'s exponent (which is
  built from the verbatim text, so `0.87` → ±0.005, `0.870` → ±0.0005, `1.5e3` → ±50). The band
  is **closed** at both ends — at an exact half-unit boundary the rounding convention is unknown,
  so the boundary errs away from `DIVERGED`. A re-derived value inside the band is `REPRODUCED`,
  and the record carries the band that decided it. This **revises** `ARCHITECTURE.md`'s
  "`REPRODUCED` = matches exactly": rounding is how the paper stated the number, not a
  tolerance, and treating it as a mismatch would make every rounded number a false `DIVERGED`.
- **D2 — Tolerance is explicit, on the binding.** A binding may carry `tolerance: {"abs":
  "<decimal>"}` or `{"rel": "<decimal>"}` (strings, never floats, non-negative). `rel` is
  relative to `|reported value|` (for a `Bound`, to `|magnitude|`), so the band it defines is
  `reported ± rel·|reported|`. Outside the band but inside
  the tolerance → `WITHIN-TOLERANCE`. Outside both → `DIVERGED`. No tolerance and outside the
  band → `DIVERGED`: the paper's own written precision is a defensible tolerance. There is no
  per-kind default tolerance in this slice. `NO_TOLERANCE` is emitted when no band can be read
  and none is given (see D1a) or when a relative tolerance is set against a reported zero.
- **D1a — Trailing-zero integers are ambiguous.** `10,000` could be exact or rounded to the
  thousand; a strict ±0.5 band would turn a rounded count into a false `DIVERGED`. A `Point`
  whose value is an integer ending in zero, with no explicit tolerance, is
  `UNVERIFIED: PRECISION_AMBIGUOUS`.
- **D3 — Value kinds in scope: `Point` and `Bound`.** A `Bound` (`p < 0.001`) holds when the
  re-derived value satisfies the operator against the magnitude → `REPRODUCED`; an explicit
  tolerance widens the threshold (satisfied only via the widening → `WITHIN-TOLERANCE`);
  otherwise `DIVERGED`. `PlusMinus`, `Interval`, `Range` and `Approximate` →
  `UNVERIFIED: UNSUPPORTED_VALUE_KIND` — recorded and counted, never guessed at.
- **D4 — Percent claims must declare scale.** A claim whose `units` is `%` or whose reported
  text contains `%` must have `scale` on its binding (`"1"` or `"100"`), else
  `UNVERIFIED: UNIT_UNDECLARED`. The re-derived value is multiplied by `scale` in `Decimal`
  before comparison. A `87%` vs `0.87` mismatch can therefore never surface as `DIVERGED`.
  `scale` is allowed on any binding (e.g. `"1000"` for s → ms); it is *required* only for
  percent claims.
- **D5 — `DIVERGED` carries `review_required: true`.** No grey zone: the verdict is binary
  past the tolerance. Nothing in C4 publishes; the flag is the R2 human-in-the-loop hook for
  C5/C6.
- **D6 — Bindings are a user-written JSON file; three deterministic locators; no model.**
- **D7 — An artifact coarser than the paper is undecidable, not divergent** (approved at the
  review gate, 2026-09-25). A script
  that prints `f"{auc:.2f}"` writes `0.87`; the paper reports `0.8712` (band ±0.00005). Under
  D1/D2 as written that is `DIVERGED`, yet the artifact's own output is *consistent* with the
  paper — it just cannot resolve that precision. That is a false `DIVERGED` on a common
  pattern. Rule: when the located text's written precision is coarser than the
  paper's, the artifact's own half-unit interval is used; if it contains the paper's value the
  verdict is `UNVERIFIED: ARTIFACT_PRECISION_COARSER` (the claim can't be decided at the
  precision the paper asserted), and if it does not, `DIVERGED` stands — no rounding of the
  run can reach the paper's number. Applies only to CSV/stdout text and JSON number literals,
  whose precision is written text. Pitfall to pin in a test: `Decimal("0.87") * 100` is
  `Decimal("87.00")` (exponent −2), so the artifact's precision must be computed as its
  half-unit × `scale`, never read off the scaled product's exponent.
- **D8 — Wrong bindings are audited, not guessed at** (review gate, 2026-09-25). No heuristic
  checks that a locator "mentions" the metric; `review_required` plus the recorded locator and
  artifact hash are the backstop for this slice (R3 below).

## Requirements

### Must-have

**M1 — Bindings file.** JSON: `{"bindings": [{"claim_id", "artifact", "locator", "tolerance"?,
"scale"?}, ...]}`. `artifact` is a captured relpath or `<stdout>`; `<stderr>` is refused
(diagnostic-only). A malformed file, a duplicate `claim_id`, or a `claim_id` not among the
input claims — or duplicate `Claim.id`s in the input claim set — raises `BindingInvalid`
(named, whole-file) — a binding to nothing is never
silently ignored. An individual entry with an invalid locator (bad pointer syntax,
uncompilable regex, a regex without exactly one group) is `UNVERIFIED: BINDING_INVALID` for
that claim.

**M2 — Locators** (the locator grammar):

| Kind | Spec | Unique-match rule |
|---|---|---|
| `json_pointer` | RFC 6901 pointer into a `.json` artifact | pointer resolves to exactly one scalar; a duplicate object key anywhere on the path → `AMBIGUOUS_BINDING` |
| `stdout_regex` | Python regex, exactly one capture group, over `<stdout>` decoded UTF-8 | exactly one match, else `NO_BINDING` (0) / `AMBIGUOUS_BINDING` (>1) |
| `csv_cell` | `{"column", "row": {"<key column>": "<key value>"}}` over a `.csv` artifact with a header row | exactly one row matches the key and the column exists exactly once in the header |

Every located value is read only through `Capture.read(artifact)` (hash re-checked). Located
text is parsed to `Decimal` with no `float` anywhere: JSON via `parse_float=Decimal,
parse_int=Decimal`, JSON `NaN`/`Infinity`/booleans/strings that aren't strict decimals →
`UNPARSEABLE_VALUE`; CSV/stdout text via strict `Decimal(text.strip())`. The verbatim located
text is kept on the record.

**M3 — Compare** per D1–D4 and D7 on `Decimal` components, never on `ClaimValue.text` identity.

**M4 — Run-outcome precedence.** `verify_claims` accepts either a completed run
(`RunTrace` + `Capture`) or a no-run cause (`ENTRYPOINT_MISSING`, `ENTRYPOINT_AMBIGUOUS`,
`ENV_BUILD_FAILED` — raised by C2/C3 before any trace exists). Order, first match wins:
1. no run → every claim `UNVERIFIED` with that cause;
2. `trace.failure` (`WONT_RUN`, `TIMEOUT`) → every claim `UNVERIFIED` with it — "the run's
   failure governs the verdict" (`run/capture.py`), even if outputs were captured;
3. `NO_ARTIFACT` → every claim `UNVERIFIED: NO_ARTIFACT`;
4. per claim: no binding → `NO_BINDING`; binding targets a `StaleOutput` relpath →
   `STALE_ARTIFACT` (its bytes are never read); target not captured → `NO_BINDING`; then
   locate → parse → kind check (D3) → scale check (D4) → compare.

**M5 — Closed cause vocabulary.** C3's `WONT_RUN`, `TIMEOUT`, `NO_ARTIFACT`,
`STALE_ARTIFACT`, `ENTRYPOINT_MISSING`, `ENTRYPOINT_AMBIGUOUS`, `ENV_BUILD_FAILED`, plus C4's
`NO_BINDING`, `AMBIGUOUS_BINDING`, `BINDING_INVALID`, `UNPARSEABLE_VALUE`, `NO_TOLERANCE`,
`UNSUPPORTED_VALUE_KIND`, `UNIT_UNDECLARED`, `PRECISION_AMBIGUOUS`,
`ARTIFACT_PRECISION_COARSER`. `PROPOSER_UNGROUNDED` and
`MODEL_ONLY_SIGNAL` (`ARCHITECTURE.md`) stay reserved and unemitted — no proposer exists. Every
cause has a test; any emitted cause outside the vocabulary fails a test.

**M6 — Verdict record.** `claim_id`, `verdict`, `cause` (present iff `UNVERIFIED`), reported
value text, located text and its `Decimal` (after scale), the band and/or tolerance that
decided it, `delta`, the locator, artifact relpath + sha256, `run_id` (null when no run), and
`review_required`. `DIVERGED` / `REPRODUCED` / `WITHIN-TOLERANCE` are only constructible with
the full evidence set (fresh artifact hash, parsed value, decided band/tolerance) — the record
type refuses otherwise.

**M7 — Canonical serialization** of the verdict set: one JSON document, sorted keys, no
incidental whitespace, `Decimal`s as text, records ordered by `claim_id`, plus the coverage
summary. Cross-process byte identity pinned by test.

**M8 — Load-bearing false-`DIVERGED` guard.** A parametrized test over every C3 cause and
every C4 binding cause asserts `UNVERIFIED`, never `DIVERGED`; a mutation check (precedence
step 2 removed; stale target treated as capturable) fails the suite.

### Should-have

- **S1 — Coverage summary** (G1) in the serialized document. A claim counts as **bound**
  when a value was located and parsed (it reached the comparison), whatever the verdict; the
  summary never folds `UNVERIFIED` into a pass or fail rate.
- **S2 — End-to-end test** through a synthetic local repo: C2 `resolve_local` → C3
  `run_and_capture` → C4 `verify_claims`, covering one of each verdict.
- **S3 — Docs on landing:** `CLAUDE.md`, `README.md`, `CAPABILITY_ROADMAP.md` C4 status,
  `ARCHITECTURE.md` C4 status + the tolerance/locator open questions marked resolved for this
  slice, and the D1 revision of the `REPRODUCED` row.

### Nice-to-have

- A small `tools/` demo that verifies a hand-written claim set against a synthetic repo and
  prints the verdict table (dev-time only, like `tools/demo_env_build.py`).

## Technical Considerations

- **Capability C4**, package `src/plumb/verify/` (per `ARCHITECTURE.md`); tests in
  `tests/verify/`. Depends on C1 (`plumb.extract` `Claim`/`ClaimValue`) and C3 (`plumb.run`
  `RunTrace`/`Capture`/`StaleOutput`) — both built. No new dependency: `json`, `csv`, `re`,
  `decimal`, `hashlib` from the standard library.
- **Verdict impact: this is the first code that emits one.** Execution decides: every compared
  value is read by hash from a fresh artifact of a run that succeeded; no model is in the
  path; bindings are user-written.
- **Determinism:** no wall clock, no absolute paths, no environment on the record; `Decimal`
  arithmetic under a pinned local context (not the thread default) so precision can't drift.
- **Float-free:** a test asserts no `float` reaches a comparison (the R2 seed the C1 record
  layer already guards against).

## Proposed aspects

| Aspect | Boundary | Depends on |
|---|---|---|
| `locators` | bindings-file schema + `BindingInvalid`, the three locators, strict `Decimal` parsing, reading only via `Capture.read` → located value or a named cause | C3 |
| `compare` | precision band (D1/D1a), tolerance (D2), `Point`/`Bound` (D3), scale (D4) → verdict + cause; pure `Decimal`, no I/O | C1 |
| `verdict-seam` | `verify_claims`, run-outcome precedence (M4), the evidence-enforcing record (M6), canonical serialization + coverage (M7/S1), the false-`DIVERGED` guard (M8), E2E (S2), docs (S3) | `locators`, `compare` |

`locators` and `compare` are independent and can proceed in parallel.

## Risks & Open Questions

- **R1 — Coverage on real papers is untested.** Synthetic repos prove the logic, not the
  coverage. **Open (owner):** the Phase 0 gate needs a real, public, runnable Python paper;
  none of the five fixtures qualifies offline (HRS / UK Biobank gated data, a large LEMUR
  corpus). Choosing it — and authorizing its network fetch — is a separate step.
- **R2 — D1's closed band and D2's "no tolerance → `DIVERGED`"** are the two choices that decide
  whether a real paper's rounded number diverges. They are pinned here and revisited only with
  evidence from the gate paper; D5's `review_required` is the backstop.
- **R2 — `Bound` strictness.** `p < 0.001` against a re-derived `0.001` is `DIVERGED` without a
  tolerance. Papers write thresholds, not rounded values, so this is intended — flagged in case
  the gate paper shows otherwise.
- **R3 — A wrong binding** (user points at the wrong key) that happens to land outside the
  band produces a `DIVERGED` that is the binding's fault. Unavoidable without a second signal;
  `review_required` plus the recorded locator and artifact hash make it auditable.
- **Open:** whether `%` vs percentage points needs its own unit rule (C1 left it open,
  `claim.py:98-100`); this slice only requires `scale`.

## Out of Scope

- A model or heuristic binding proposer; any use of `artifact_hint` beyond carrying it.
- `PlusMinus`, `Interval`, `Range`, `Approximate` comparison (→ `UNSUPPORTED_VALUE_KIND`).
- Notebook-cell locators (C3 notebook capture is itself a follow-on).
- The `plumb verify` CLI (no CLI exists yet; Phase 1).
- Choosing or running the gate paper; the C5 corpus; C6 bundling and signing.
- Per-kind default tolerances.
