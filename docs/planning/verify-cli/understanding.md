# verify-cli — understanding note

What the work is really asking, after the deep dig (2026-09-27). Grounds the PRD.

## What this is

The first user-facing surface of the engine: `plumb verify <paper> <repo> [--rev REV]
[--out bundle/]` runs the C1→C2→C3→C4→C6 spine and prints a per-claim verdict table plus
`UNVERIFIED`-with-cause, writing a signed bundle. It is Phase 1's headline deliverable
(`docs/ROADMAP.md:37-39`) and the target CLI shape is already specced
(`docs/technical/ARCHITECTURE.md:189-192`). There is **no CLI today**: no `[project.scripts]`
entry, no `__main__.py`, no argparse/click/typer anywhere — the spine is wired only by
`tools/*.py` scripts run via `uv run tools/x.py`.

## The seams it binds (all exist, all tested)

- C1: `extract_claims(raw: str)` (`src/plumb/extract/pipeline.py:29`) — paper *text*, not a path;
  PDFs via `pdf_to_markdown(data: bytes)` (`src/plumb/pdf/__init__.py:22`). `paper_text(bytes,
  format)` already centralizes bytes→text in `src/plumb/bundle/verify.py:185`.
- C2: `resolve_git(url, rev=None)` / `resolve_local(path)` / `resolve_archive(path)` →
  `Checkout` (`src/plumb/intake/checkout.py:70-166`); `describe_environment` →
  `EnvDescriptor` (`env.py:97-117`). **Offline guard:** `build_environment` raises
  `EnvBuildFailed` without a runner (`env.py:132-136`) — the real `uv sync` is dev-time-only
  by convention (`intake/__init__.py:24-29`), so the CLI's live path must own that choice and
  tests must stub the env build.
- C3: `run_and_capture(checkout, env_build, entrypoint, ...) -> (RunTrace, Capture)`
  (`run/__init__.py:82-95`); `resolve_entrypoint` raises `EntryPointMissing`/`Ambiguous`.
- C4: `verify_claims(claims, bindings, Completed(trace, capture) | NoRun) -> VerdictSet`
  (`verify/__init__.py:130-154`); `load_bindings(raw: bytes, claim_ids)` (`bindings.py:105`);
  `NoRun.from_exception` maps pre-run failures to all-`UNVERIFIED` (`verify/__init__.py:120-127`).
  `VerdictSet.coverage` (`verdict.py:128-140`) is the summary input for the printed table.
- C6: `build_bundle(out, *, claims, paper: bytes, paper_format, ..., bindings: bytes, trace,
  capture, environment: str, source, signer) -> Path` (`bundle/build.py:53-119`) — takes
  values, re-derives verdicts itself, refuses to sign what `verify_bundle` would reject.
  Signing key: private at `~/.ssh/plumb_bundle_ed25519` (outside repo), public in
  `bundles/allowed_signers`, principal `plumb-bundle` (`bundle/sshsig.py:28-70`).

## The offline acceptance path (the wrinkle)

The committed gate record is `fixtures/gate/agrodesign/` (paper.pdf, claims.json, bindings.json,
trace.json, verdicts.json, environment.txt, objects/). `tests/gate/test_agrodesign_replay.py`
replays it byte-identical (86 claims, 85 REPRODUCED / 1 DIVERGED). **But C1-extracted claim ids
are disjoint from the curated claim ids** (`tests/gate/test_agrodesign_fixture.py:95-101`) —
C1 recovers 86/86 *by place and value*, not by id — so a CLI that runs `extract_claims`
end-to-end cannot reuse the committed `bindings.json` as-is (orphan ids → `BindingInvalid`).
The offline CLI test must therefore either re-admit the curated claims via `readmit`
(`admit.py:441`) or exercise a committed-record replay path. This is the single biggest design
fork for the PRD: **does the CLI verify a live repo (real run) or replay a committed record,
or both?**

## Open questions for the interview

1. Live run vs committed-record replay as the CLI's primary mode — both? `--from-record`?
2. Bindings source: does the CLI require a user bindings file (C4's contract: bindings are
   user-written, no proposer), or is there a default/empty-bindings behavior (all
   `UNVERIFIED: NO_BINDING`)? The Phase 1 shape says `--propose-claims` is the only LLM path
   (off by default, BYOK) — out of scope here.
3. `--out bundle/`: bundle always, or only with `--out`? AgroDesign bundles the paper (CC BY
   4.0); do we bundle the paper by default (`include_paper` choice)?
4. Env build: `--no-env`/stub for offline tests and for repos that need no deps? The real
   `uv sync` must remain a dev-time, explicit, user-authorized action.
5. Exit codes: 0 all-verified-clean vs non-zero on any `UNVERIFIED`/`DIVERGED` vs non-zero only
   on harness failure? The brief says "a failing repo yields non-zero exit with named
   UNVERIFIED causes, never DIVERGED".
6. Output format: human table (stdout) + canonical JSON (the determinism standard)? The brief
   requires byte-identical CLI output across invocations — one format must be the canonical one.
7. `--rev` only for git URLs; what about local paths and archives as `repo` inputs (C2 supports
   all three)?
8. Signer discovery: default `~/.ssh/plumb_bundle_ed25519` with `--signer-key` override, and
   `--no-sign` for unsigned bundles (bundle still builds, verification skips signature)?

## Placement

C4 hardening slice (binding & verdict — the moat) + C6 integration, Phase 1 of
`docs/ROADMAP.md`. Execution decides: the CLI only ever *renders* `Verdict`s from
`verify_claims`; no model opinion enters the verdict path. All guardrails hold by construction
if the CLI is a thin shell over the existing seams — the risk is the shell doing something the
seams wouldn't (path mangling, stale reads, id confusion), which is exactly what the
byte-identical replay tests pin.

## Caveat (R1)

The end-to-end path has run on exactly one paper (AgroDesign) via library calls and dev-time
tools; real-repo variance (network, uv sync, timeouts) is unmeasured. The CLI must keep every
existing guard green (`tests/verify/test_false_diverged_guard.py` mutation-checked, freshness
guard, no-network conftest).