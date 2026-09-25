# C4 Binding & verdict — understanding (deep dig, 2026-09-25)

## What the work is really asking

The Phase 0 gate's C4 minimum: "bind one headline claim to a re-derived value and emit the
verdict" (`docs/ROADMAP.md`). This is the first code in the repo that emits a verdict. C1
supplies `Claim` (`src/plumb/extract/claim.py`); C3 supplies `RunTrace` + `Capture`
(`src/plumb/run/trace.py`, `capture.py`). C4 is the join: a **binding** (claim id → locator
into one captured artifact), a **comparison** on `Decimal`s, and a **verdict record** with a
named cause.

## What the consumed code actually offers (verified)

- `Claim.reported_value` is a tagged union: `Point`, `Bound`, `PlusMinus`, `Interval`,
  `Range`, `Approximate` (`value.py`). Each carries verbatim `text` + `Decimal` parts. The
  precision the paper wrote survives only in `text` / `Decimal.as_tuple().exponent`.
- `Claim.tolerance_hint` is **verbatim, unparsed text by design** — "a parsed numeric
  tolerance sitting here would quietly settle [the open question]" (`claim.py:108-111`).
  So C1 gives C4 no numeric tolerance: the tolerance must come from the binding (or a
  policy), and this slice is where the open question gets settled.
- `Claim.artifact_hint` is a hint, "never an assertion that it is right". No binder or
  locator source exists; the first slice's locators must be **supplied explicitly** (a
  binding record the user writes). A model proposer is out of scope (and could only propose).
- `Capture.locatable` excludes stderr; `Capture.read(artifact)` re-checks the SHA-256. A
  `StaleOutput` has no bytes at all — it can never be parsed, only reported.
- `RunTrace.failure` carries `WONT_RUN` / `TIMEOUT`; `RunTrace.causes` carries
  `NO_ARTIFACT`; `RunTrace.stale` carries `STALE_ARTIFACT` records.
  **`ENTRYPOINT_MISSING`, `ENTRYPOINT_AMBIGUOUS` and `ENV_BUILD_FAILED` are raised
  exceptions — no `RunTrace` exists for them.** C4 must therefore accept "no run" plus a
  cause as an input, not just a trace.

## Affected areas

New package `src/plumb/verify/` (per `ARCHITECTURE.md`): locators, tolerance, compare,
verdict record + canonical serialization, a `verify_claims` seam. Tests under
`tests/verify/`, offline, synthetic repos run through C3's real `run_and_capture` with local
programs (the C3 test pattern). Docs to update on landing: `CLAUDE.md`, `README.md`,
`CAPABILITY_ROADMAP.md` C4 status, `ARCHITECTURE.md` C4 status + open questions.

## Ambiguities / open questions (for the PRD interview)

1. **Precision vs tolerance (the R2 trap).** A paper writes `0.87`; the run prints
   `0.8712`. Rounded to the paper's written precision these agree. Is that `REPRODUCED`,
   `WITHIN-TOLERANCE`, or does it need an explicit tolerance? If precision-rounding is not
   honoured, every rounded number in every paper is a false `DIVERGED` — reputational poison.
2. **Where tolerance comes from.** Per-binding explicit, a typed default per value kind, or
   both. How "no defensible tolerance" is represented (`NO_TOLERANCE`).
3. **Which value kinds this slice compares.** `Point` and `Bound` have clear semantics.
   `PlusMinus` (margin meaning unstated), `Interval`, `Range` need a decision on *which
   component* a locator binds to; `Approximate` has no stated precision. Candidate: out of
   scope for the slice, resolving to a named `UNVERIFIED` cause.
4. **Units/scale.** Paper says `87%`, the run writes `0.87`. That is a binding-side
   mismatch — must never be `DIVERGED`. Explicit scale on the binding, or `UNVERIFIED`?
5. **The DIVERGED bar.** How far outside tolerance before `DIVERGED` vs. a grey zone? The
   ROADMAP says human-in-the-loop before any finding is published — does the verdict record
   carry a "requires review" marker, or is that C6/C5's concern?
6. **Locator grammar.** Brief: JSON pointer (RFC 6901), regex over stdout (exactly one
   match, one group), CSV cell (column name + row key). Parsing the located text to
   `Decimal` must never pass through `float` (`json.loads(parse_float=Decimal)`).
7. **Gate paper.** A real public runnable paper is needed for the Phase 0 gate; none of the
   five fixtures qualifies offline. Out of scope here, flagged for owner decision.

## Contradictions surfaced

- The brief lists `ENTRYPOINT_*` as causes that "pass through" C3; in the code they are
  exceptions with no trace. The design must take a no-run input, not a trace field.
- `ARCHITECTURE.md`'s cause vocabulary lacks `TIMEOUT`, `ENTRYPOINT_*` and `ENV_BUILD_FAILED`
  though C3 emits them; the C4 vocabulary must be the union, closed and tested.

## Guardrail placement

C4 **touches verdicts**. Execution decides: every value compared is read from a captured
artifact by hash; no model is in the path; the binding is a user-supplied record in this
slice. `DIVERGED` only when a bound, fresh value from a successful run falls outside a
tolerance that was actually set.
