# Aspect `verdict-seam` — `verify_claims`, the record, and the false-`DIVERGED` guard

Parent: [`../prd.md`](../prd.md) (M4–M8, S1–S3; D5).

## Problem slice & outcome

`verify_claims(claims, bindings, run)` → `VerdictSet`: exactly one `Verdict` per input claim,
the coverage summary, and canonical bytes. `run` is either `Completed(trace, capture)` or
`NoRun(cause)` for the causes raised before any trace exists.

## In scope

- **Precedence (M4):** `NoRun` → every claim `UNVERIFIED: <cause>`; `trace.failure` → every
  claim `UNVERIFIED: WONT_RUN|TIMEOUT` (captured outputs are *not* located); `NO_ARTIFACT` in
  `trace.causes` → every claim `UNVERIFIED: NO_ARTIFACT`; otherwise per claim: no binding →
  `NO_BINDING`, else `locators` then `compare`.
- `NoRun` accepts only `ENTRYPOINT_MISSING`, `ENTRYPOINT_AMBIGUOUS`, `ENV_BUILD_FAILED`, and
  offers `NoRun.from_exception(exc)` reading the exception's `cause` attribute (C3's
  exceptions carry one; C2's `EnvBuildFailed` is checked and mapped).
- `trace` and `capture` must describe the same run (`derive_run_id` over the capture equals
  `trace.run_id`), else `ValueError` — a verdict against another run's outputs is refused.
- **`Verdict` record (M6):** fields per the PRD; constructor refuses a non-`UNVERIFIED`
  verdict missing the artifact sha256, located text, decided band/tolerance or `run_id`; refuses
  `UNVERIFIED` without a cause and a cause on a non-`UNVERIFIED`; `review_required` is
  `verdict == DIVERGED`, derived, not supplied.
- **Closed vocabulary (M5):** `CAUSES` frozenset; the record refuses any other cause.
- **Serialization (M7):** canonical JSON document `{"run_id", "verdicts": [...by claim_id],
  "coverage": {...}}`, `Decimal`s as text, registry-style encoder that refuses unknown types
  (the `plumb.extract.serialize` contract).
- **Coverage (S1):** `claims`, `bound` (reached `compare`), per-verdict counts, per-cause
  counts; every count derived from the records, never tracked separately.
- **Public seam:** `plumb.verify.__init__` exports and a module docstring with the cause
  table, like `plumb.run`.
- **Docs (S3)** updated in the same aspect.

## Out of scope

CLI, corpus banking, bundle/signing, gate paper.

## Acceptance criteria (failing tests first)

1. One record per claim, sorted by `claim_id`; a claim with no binding is present as
   `NO_BINDING` — never dropped.
2. Parametrized false-`DIVERGED` guard over every C3 cause (`NoRun` ×3, `WONT_RUN`,
   `TIMEOUT`, `NO_ARTIFACT`, `STALE_ARTIFACT`) with a binding whose value *would* diverge:
   every record is `UNVERIFIED` with that cause, none `DIVERGED`.
3. Mutation check: the guard test is run against a patched precedence (step 2 removed) and
   against a `locate` that reads stale targets; each patched run makes the guard fail (asserted
   in-suite, like C3's freshness mutation check).
4. A `WONT_RUN` run whose captured JSON holds a perfectly matching value still yields
   `UNVERIFIED: WONT_RUN` — never `REPRODUCED`.
5. Mismatched `trace`/`capture` raises `ValueError`.
6. `Verdict(verdict=DIVERGED, …)` without evidence fields raises; `UNVERIFIED` with an
   out-of-vocabulary cause raises; every cause in `CAUSES` is emitted by at least one test.
7. Serialization is byte-identical across two subprocesses; no absolute path or
   `started_at_ns` in the bytes; a `float` smuggled into a record makes the encoder raise.
8. Coverage counts equal the counts recomputed from the records; `UNVERIFIED` never counted as
   bound unless it reached `compare` (e.g. `ARTIFACT_PRECISION_COARSER` counts as bound).
9. E2E (S2): a synthetic local repo whose `main.py` writes `results.json`, `table.csv` and
   prints to stdout, resolved by C2 `resolve_local` and run by C3 `run_and_capture`, verified
   against hand-built `Claim`s → one `REPRODUCED`, one `WITHIN-TOLERANCE`, one `DIVERGED`, one
   `UNVERIFIED: STALE_ARTIFACT` (committed back-dated file), one `NO_BINDING`.

## Dependencies & sequencing

Needs `locators` and `compare` merged into the branch first.

## Risks

- R2: criteria 2–4 are the load-bearing tests. They must fail loudly if anyone reorders the
  precedence.
