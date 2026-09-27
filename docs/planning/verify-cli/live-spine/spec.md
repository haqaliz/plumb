# live-spine — aspect spec

Problem slice: `plumb verify <paper> <repo> [--rev REV] [--bindings FILE] [--no-env-build]
[--out DIR]` — the live end-to-end path: extract claims from the paper, resolve and pin the
repo, build the environment, run the entry point, capture outputs, bind and decide, print the
table, optionally write the signed bundle. The demo path — and the surface R1 gets measured
on (paper #2 is now one command).

## In-scope requirements

- Paper input: `<paper>` is a `.md` or `.pdf` path. PDF → `pdf_to_markdown`
  (`src/plumb/pdf/__init__.py:22-27`; `PdfInputError` → `PAPER_UNREADABLE`); markdown → read
  bytes → decode. Unreadable/missing → `PAPER_UNREADABLE` (exit 1).
- Claims: `extract_claims(text)` (`src/plumb/extract/pipeline.py:29-31`); a vacuous paper
  (zero claims) is a valid run — render the empty table, exit 0 if the run itself succeeded.
- Repo input: local directory (`resolve_local`), `https` git URL with optional `--rev`
  (`resolve_git`), or archive path (`resolve_archive`) — `src/plumb/intake/checkout.py:70-166`.
  Resolution failures → their named causes.
- Environment: `describe_environment` then `build_environment` with the real
  `uv_sync_runner` by default; `--no-env-build` substitutes the offline stub (no runner →
  `EnvBuildFailed` guard, `src/plumb/intake/env.py:132-136`, must be bypassed only by the
  stub path). Real `uv sync` runs only when the user invokes live mode without
  `--no-env-build` — dev-time, never in CI (tests always stub).
- Run: `resolve_entrypoint` (explicit wins; else one `[project.scripts]` entry or root
  `main.py`; none/many → `ENTRYPOINT_MISSING`/`ENTRYPOINT_AMBIGUOUS`) then
  `run_and_capture` with an explicit absolute `run_dir` under the CLI's work area
  (default is relative, `src/plumb/run/runner.py:158-168`) and the default timeout.
- Bindings: `--bindings FILE` required; `load_bindings` on the file bytes with the extracted
  claim ids; refusal → `BINDING_INVALID` (exit 1). No bindings → usage error (exit 2).
- Verdicts: `verify_claims(claims, bindings, Completed | NoRun.from_exception(...))`
  (`src/plumb/verify/__init__.py:120-154`) — run-level causes govern first, so no harness
  failure becomes `DIVERGED`.
- `--out DIR`: `build_bundle` with the extracted claims, paper bytes (included by default,
  `--no-paper` to omit), bindings bytes, trace, capture store, environment text, source
  record, signer from `~/.ssh/plumb_bundle_ed25519` or `--signer-key` (missing key →
  `KEY_MISSING`, exit 1, no bundle written); bundle must pass `verify_bundle` (build refuses
  otherwise → `BUNDLE_REFUSED`).
- Output: shared renderer (table or `--json`); exit per PRD contract.

## Out-of-scope boundaries

- No `--propose-claims` / LLM assist; no `--tolerance` (tolerances live in the bindings file).
- No `--timeout-seconds`/`--run-dir` flags (should-have, next slice).
- No notebook capture, no container isolation, no resource caps (C3 follow-ons).
- No writing into the repo checkout or the pinned tree (C3's working-copy rule stands).

## Acceptance criteria (testable, written failing first — all offline)

1. End-to-end on a synthetic repo (pattern: `tests/verify/test_verify_e2e.py:53-99`): a
   local fixture repo whose `main.py` writes a JSON artifact, a small markdown paper, a
   bindings file, `--no-env-build` → exit 0, verdict table + `--json` output correct
   (claims bound, `REPRODUCED` where the artifact matches), run recorded in the run area.
2. The same synthetic paper with bindings pointing at a value the artifact doesn't contain →
   exit 1 with the claims `UNVERIFIED` (`NO_BINDING`) — table renders, exit is non-zero,
   never `DIVERGED`.
3. A repo that fails to resolve (missing path / bad rev) → exit 1, named cause on stderr,
   no traceback.
4. A repo whose entry point doesn't exist → exit 1, `ENTRYPOINT_MISSING` on stderr, all
   claims `UNVERIFIED` with that cause in the table (run-level cause governs — the
   false-`DIVERGED` guard holds through the CLI).
5. `--no-env-build` is honored (no runner ever constructed); live mode without it in tests
   still cannot reach the network (conftest) — the test proves the stub path is the only
   tested path.
6. `--out` on the synthetic run writes a bundle that `verify_bundle` accepts (ephemeral
   test key); paper included by default, omitted with `--no-paper`.
7. Determinism: two invocations on the same inputs (same process) produce byte-identical
   stdout; run_dir must be derived deterministically from inputs (recorded, not wall-clock).
8. Zero-claim paper + runnable repo → exit 0 with an empty verdict table and empty `--json`
   verdicts array.

## Dependencies and sequencing

Depends on cli-core (dispatch, exit codes) and render (output). Reuses replay's knowledge of
bundling in tests (ephemeral keys, `verify_bundle`). The real AgroDesign run is a dev-time
demo via the CLI (`uv run plumb verify fixtures/gate/agrodesign/paper.pdf <git-url> --rev ...`)
— recorded in the PR, never in CI.

## Open questions / risks

- R1 (High/High): the live path's real-world variance (network, uv sync, timeouts) is
  unmeasured; this aspect makes it measurable but does not retire it. The dev-time demo run
  is the acceptance evidence for the real path.
- `run_dir` derivation: must be deterministic for byte-identical output (e.g.
  `runs/verify-<tree-digest12>-<ns>` seeded from the run's inputs) — confirm the existing
  default in `runner.py:158-168` and override with a CLI-owned dir whose name derives from
  the tree hash + argv hash, recorded in the trace.
- Stub env build: must reuse the existing test stub (`tests/verify/verify_helpers.py`) shape;
  the CLI's `--no-env-build` path must construct the same offline `EnvBuild` the e2e test
  uses, never the real runner.