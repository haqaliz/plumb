# Understanding — BYOK binding proposer (#24)

## What the work really is

The demo works; a stranger cannot verify *their own* paper because bindings are hand-written. The
gap is not "call a model" — it is **keeping the verdict contract intact while a model helps**.

The design that makes that true with almost no new code: the proposer's output *is a bindings
document*. It goes through `load_bindings` and `verify_claims` exactly like a hand-written file,
so a proposal structurally cannot assign a verdict.

## Affected areas

| Area | Change |
|---|---|
| `src/plumb/propose/` | new: request document, command runner, per-proposal grounding |
| `src/plumb/cli/__init__.py` | `--proposer`; exactly-one-of rule; from-record rejection |
| `src/plumb/cli/live.py` | propose after the run (a cap/capture exists only then) |
| `src/plumb/verify/causes.py` | the `RESERVED` docstring: the proposer now exists, the names stay out of `CAUSES` |

## Decisions

- **The user supplies the command** (`--proposer CMD`), not a provider integration: no SDK, no
  model name, no network code, no key handling in this repo. BYOK literally.
- **Grounding is four checks** and each refusal is named: unknown claim / artifact the run did not
  write → `PROPOSER_UNGROUNDED`; locator finds nothing unique and fresh → `MODEL_ONLY_SIGNAL`; the
  command fails → `PROPOSER_FAILED` (a CLI cause, mapped like the rest).
- **The dropped proposal is not a verdict cause.** The claim falls through to `NO_BINDING`, which
  is the honest vocabulary. `RESERVED` stays reserved, now for the right reason.
- **Proposal after the run, before verify.** A failed run skips the proposer: there is nothing to
  bind against, and a model call would be waste.
- **The bundle carries the accepted bindings**, which is the property that matters: the model is
  provenance, the run is evidence, and a third party replays without either.

## Pipeline placement

C4 (binding). The moat is unchanged: a proposal is never a verdict.
