# PRD — BYOK binding proposer

Issue: #24. The largest product gap; deliberately off the launch path.

## Requirements

- **R1** — `plumb verify ... --proposer CMD`; exactly one of `--bindings` / `--proposer`; both,
  neither, or either with `--from-record` is a usage error (2).
- **R2** — the proposer command receives a JSON request on stdin with the claims (id, metric,
  reported text, units) and the run's locatable artifact paths only — no paper bytes, no captured
  contents — and writes a bindings-shaped document on stdout.
- **R3** — every proposal is re-grounded: known claim, artifact the run wrote, locator valid under
  `load_bindings`, and `locate` returns exactly one fresh value. Refusals are printed with
  `PROPOSER_UNGROUNDED` / `MODEL_ONLY_SIGNAL`; a failed command is `PROPOSER_FAILED`, exit 1.
- **R4** — no proposal can decide a verdict: accepted proposals pass through `load_bindings` +
  `verify_claims`; a bogus locator yields `UNVERIFIED: NO_BINDING`, never `DIVERGED`.
- **R5** — accepted bindings are canonical (sorted by claim id, deduped, first grounding wins) and
  are what `--out` puts in the bundle, so the replay needs no proposer.
- **R6** — offline: tests run a local stub command; no network, no model, no key.

## Non-goals

- Provider SDKs, prompt engineering, retries, streaming.
- Proposing claims (C1's job) or tolerances beyond what the binding schema already allows.
- Auto-selecting a model or storing a key.

## Acceptance

`tests/propose/test_propose.py` (grounding + command) and `tests/cli/test_proposer_cli.py`
(argument rules, grounded run, refusals, bundle replay); full suite green.
