# verify-cli PRD — `plumb verify <paper> <repo>`

Status: drafted via prd-interview (2026-09-27), owner-confirmed decisions inline. Capability:
C4 hardening slice + C6 integration (Phase 1 headline, `docs/ROADMAP.md:37-39`). Source card:
`docs/planning/_card/issue.md`; understanding: `docs/planning/verify-cli/understanding.md`.

## Problem Statement

The engine's spine exists only as library seams (`src/plumb/extract|intake|run|verify|bundle`)
wired by owner-written `tools/*.py` scripts. Phase 1's deliverable — "Ship the self-hostable
CLI: C1–C4 hardened + C6 … `plumb verify <paper> <repo>` returns a per-claim verdict table and
a bundle" (`docs/ROADMAP.md:37-39`) — does not exist: no `[project.scripts]` entry, no
`__main__.py`, no argparse/click/typer anywhere. Without the CLI there is no OSS on-ramp
(`VISION.md:66-68`), and R1 (binding coverage, High/High, `docs/ROADMAP.md:62`) stays unmeasured
because running paper #2 means hand-writing another tool script.

## Goals & Success Metrics

- **Goal:** `plumb verify` becomes the single command that runs a paper's spine end-to-end and
  prints a per-claim verdict table, with an offline replay mode that CI can test byte-identically.
- **Success metric 1 (determinism):** two invocations of `plumb verify` on the same input
  produce byte-identical stdout (table + JSON) — pinned by tests, matching the engine's
  canonical-JSON contract (`src/plumb/extract/serialize.py:81-129`).
- **Success metric 2 (replay):** `plumb verify --from-record fixtures/gate/agrodesign/`
  reproduces the committed verdicts byte-identically: 86 claims, 85 `REPRODUCED`, 1 `DIVERGED`
  (`tests/gate/test_agrodesign_replay.py:73-86`).
- **Success metric 3 (guards hold):** the existing suite stays green (1532 tests), including the
  mutation-checked false-`DIVERGED` guard (`tests/verify/test_false_diverged_guard.py`) and the
  no-network conftest (`tests/conftest.py:56-60`).

## User Personas & Scenarios

- **The owner / a future design partner (journal, lab):** `plumb verify paper.pdf repo-url
  --rev v1.2 --bindings bindings.json --out bundle/` → reads the verdict table on stdout, gets a
  signed replayable bundle a third party can `verify_bundle`.
- **The CI system:** `plumb verify --from-record fixtures/gate/agrodesign/ --json` → exit code
  is the scriptable signal; stdout is canonical JSON (or a fixed-format table).
- **A paper author:** runs the CLI against their own repo to see, per claim, whether their
  reported numbers hold against their own code's run.

## Requirements

### Must-have (this slice)

1. **`plumb verify <paper> <repo>`** — live mode, the default. `<paper>` is a `.md` or `.pdf`
   path (PDF via the pinned `pdf_to_markdown`); `<repo>` is a local directory, an `https` git
   URL (with `--rev REV`), or an archive path (tar.gz/tgz/zip) — C2's three input kinds.
2. **`--bindings FILE` (required in live mode)** — C4's contract: bindings are user-written
   (`src/plumb/verify/bindings.py:105-123`); without it the CLI exits non-zero with a usage
   error. No proposer; no `--propose-claims` in this slice (BYOK path stays a later slice, off
   by default).
3. **Live spine:** extract claims (C1) → resolve checkout (C2) → describe environment + build
   it (real `uv sync` by default; `--no-env-build` skips with the offline stub) → resolve entry
   point + run + capture (C3) → `verify_claims` (C4) → print table + JSON.
4. **`--from-record <dir>`** — replay mode: reads the record's own `claims.json`,
   `bindings.json`, `trace.json`, `objects/` (e.g. `fixtures/gate/agrodesign/`), re-derives
   verdicts via `verify_claims` on `Completed(trace, capture)`, prints the same table + JSON.
   No `<paper>`/`<repo>`/`--bindings` args; the record carries everything. Supports `--out`.
5. **`--out DIR`** — writes the signed bundle via `build_bundle`
   (`src/plumb/bundle/build.py:53-119`); signer key defaults to `~/.ssh/plumb_bundle_ed25519`
   (principal `plumb-bundle`, `src/plumb/bundle/sshsig.py:28-70`), `--signer-key PATH` overrides;
   a missing key is a clear error and no bundle is written (no `--no-sign` escape hatch). Paper
   is included in the bundle by default (`--no-paper` to omit). Bundle must pass
   `verify_bundle` — `build_bundle` refuses to sign anything it would reject.
6. **`--json`** — emits the machine contract: canonical JSON (the engine's
   `sort_keys=True, ensure_ascii=False, separators=(",",":")` convention) containing the
   per-claim verdicts (same fields as `serialize_verdicts`, `src/plumb/verify/serialize.py:40-47`)
   plus the coverage summary (`VerdictSet.coverage`, `src/plumb/verify/verdict.py:128-140`).
   Without `--json`, stdout is a fixed-layout human table (no timestamps, no cwd, no env
   variance — byte-identical across invocations).
7. **Exit-code contract:** 0 when every claim is *decided* (`REPRODUCED` /
   `WITHIN-TOLERANCE` / `DIVERGED` — the engine did its job) and the run itself succeeded;
   non-zero when anything is `UNVERIFIED`, when the spine failed (resolve/run/bind/bundle
   error), or on usage error. **Never** exit 0 with a `DIVERGED` hidden; a harness failure is
   never rendered `DIVERGED` (the `NoRun.from_exception` mapping,
   `src/plumb/verify/__init__.py:120-127`).
8. **Determinism:** two invocations on the same input → byte-identical stdout. The CLI output
   joins the engine's canonical-JSON family; cross-process determinism pinned by tests
   (per `tests/extract/test_determinism.py` precedent).
9. **Offline testability:** the suite runs with no network (conftest blocks sockets). Live
   mode's env build is stubbed in tests (`tests/verify/verify_helpers.py` stub `EnvBuild`);
   the real `uv sync` runs only in dev-time demos, never in CI (`docs/technical/CAPABILITY_ROADMAP.md:110-111`).

### Should-have

10. `--timeout-seconds` / `--run-dir` passthroughs to `run_and_capture` (the C3 seam exposes
    them; defaults already pinned, `src/plumb/run/__init__.py:82-95`). *Not in the minimal
    flag set per owner decision — listed here as the immediate follow-on knob.*

### Nice-to-have (later slices)

- `--propose-claims` (BYOK, opt-in, off by default — ARCHITECTURE.md:192).
- `--tolerance` CLI override (tolerances live in the bindings file today, per C4 D1/D2).
- `plumb bundle` as a separate subcommand; tar packaging (C6 follow-ons).
- Notebook capture + notebook-cell locators (C3/C4 follow-ons, R1 mitigation).

## Technical Considerations

- **The CLI is a thin shell over the seams — nothing re-implemented.** `extract_claims`,
  `resolve_git`/`resolve_local`/`resolve_archive`, `describe_environment` +
  `build_environment`, `resolve_entrypoint` + `run_and_capture`, `load_bindings` +
  `verify_claims`, `build_bundle` + `verify_bundle`. The guards (freshness,
  false-`DIVERGED`, admission gate) hold by construction because the CLI never bypasses them.
- **Entry point:** `[project.scripts]` in `pyproject.toml` + `src/plumb/cli.py` (stdlib
  `argparse` — no new dependency; the engine pins exactly one runtime dep, pypdf).
- **The claim-id wrinkle (the reason `--from-record` exists):** C1-extracted claim ids are
  disjoint from the curated ids in `fixtures/gate/agrodesign/claims.json`
  (`tests/gate/test_agrodesign_fixture.py:95-101`), so live mode cannot reuse the committed
  bindings; the replay path uses the record's own claims+bindings — that is precisely why the
  offline acceptance path must be `--from-record`, not live-with-committed-bindings.
- **Run area:** live mode passes an explicit absolute `run_dir` under its own work area (the
  default is relative, `src/plumb/run/runner.py:158-168`).
- **Env build is a real, user-authorized action in live mode** — the CLI is where `uv sync`
  becomes user-facing; the offline guard (`build_environment` raises `EnvBuildFailed` without
  a runner, `src/plumb/intake/env.py:132-136`) is preserved: tests never supply the real
  runner.
- **Paper handling:** paper bytes → `pdf_to_markdown` (PDF) or decode (markdown) → `hash_paper`
  → claims. `paper_text(bytes, format)` already centralizes bytes→text
  (`src/plumb/bundle/verify.py:185-191`).

## Non-Functional Requirements

- Determinism: byte-identical stdout across processes (PYTHONHASHSEED variance included).
- No network in tests; no new runtime dependency.
- Exit codes stable and documented in `--help`.
- All existing guards stay green (1532 tests at base).

## CLI-Level Failure Contract (named causes)

The CLI maps every failure to a named cause and exit code 1 (usage errors = exit 2). No
tracebacks reach stdout. The spine's own causes pass through unchanged (they are the engine's
closed vocabulary — `src/plumb/verify/causes.py:82-101`, intake/run cause tables).

| Cause | When | Source |
|---|---|---|
| `USAGE_ERROR` | bad flags, missing required arg, unknown input kind | CLI argument parsing |
| `PAPER_UNREADABLE` | `<paper>` path missing, unreadable, or PDF conversion fails | `pdf_to_markdown` / `PdfInputError` |
| `SOURCE_NOT_FOUND` / `REV_NOT_FOUND` / `UNSUPPORTED_ARCHIVE` | C2 resolution failure | `src/plumb/intake/causes.py:19-31` |
| `ENV_BUILD_FAILED` | real env build failed (live mode, no `--no-env-build`) | `src/plumb/intake/env.py` |
| `ENTRYPOINT_MISSING` / `ENTRYPOINT_AMBIGUOUS` | C3 entry-point resolution | `src/plumb/run/entrypoint.py:61-70` |
| `WONT_RUN` / `TIMEOUT` / `NO_ARTIFACT` / `STALE_ARTIFACT` | C3 run-level causes (→ all claims `UNVERIFIED`) | `src/plumb/run/causes.py:31-48` |
| `BINDING_INVALID` | `--bindings` file refused, or per-entry locator invalid | `src/plumb/verify/bindings.py:105-123` |
| `RECORD_INVALID` | `--from-record` dir missing `claims.json`/`bindings.json`/`trace.json`/`objects/`, or `parse_trace` refuses a mismatched id | `src/plumb/run/trace.py:134-180` |
| `KEY_MISSING` | `--out` given and no signer key at default/`--signer-key` path | `src/plumb/bundle/sshsig.py` |
| `BUNDLE_REFUSED` | `build_bundle` refuses to sign (wouldn't verify) | `src/plumb/bundle/build.py:70-73,114-117` |
| `SPINE_ERROR` | unexpected internal failure (any non-cause exception) — bug, not user error | CLI catch-all |

Every failure prints `plumb verify: <CAUSE>: <detail>` to stderr and exits 1 (2 for usage),
never a traceback. A run-level cause produces the verdict table with all claims `UNVERIFIED`
under that cause *and* exit 1 — the table is the evidence, the exit code is the signal.

## Risks & Open Questions

- **R1 (High/High, `docs/ROADMAP.md:62`):** the end-to-end path has run on exactly one paper
  via library calls; real-repo variance (network, uv sync, timeouts) is unmeasured. The CLI
  does not retire R1 — it makes measuring it cheap (paper #2 is now one command). The
  `--from-record` path is the CI-testable surface; the live path's real run stays a dev-time
  demo.
- **R2 (High/High):** the CLI must never emit `DIVERGED` on a harness-side failure — by
  construction it only renders `Verdict`s from `verify_claims`; the exit-code contract maps
  `UNVERIFIED` to non-zero so nothing is hidden.
- **Open:** exact table layout and JSON schema for `--json` (to be fixed in the aspect spec;
  verdict fields from `serialize_verdicts` are the floor). Signer-key discovery precedence
  (env var vs flag vs default path). Whether `--from-record` should verify the record's
  committed `verdicts.json` matches the re-derivation (it should — cheap honesty check).
- **Edge cases to pin in the aspect spec:** zero claims extracted (vacuous paper — still a
  valid run, 0 claims, exit 0), all claims `UNVERIFIED` (run-level cause — table still
  renders), `--from-record` against a dir with missing members (`RECORD_INVALID`), huge
  claim sets (table pagination is out of scope; JSON is the machine path).
- **Actionable failure output:** run-level failures print the cause, detail *and a hint*
  (e.g. `--timeout-seconds` exists as a should-have knob; a `WONT_RUN` names the entry point
  resolution). The first demo's likeliest failure is a real `uv sync` on a real repo — the
  output must say what to do, not just what broke.

## Out of Scope

- `--propose-claims` / any LLM path (BYOK later slice, off by default).
- Notebook capture and notebook-cell locators (C3/C4 follow-ons).
- `PlusMinus`/`Interval`/`Range`/`Approximate` comparison (C4 not-built list).
- C5 corpus writes, C7 no-code checks, C8 hosted layer.
- `plumb bundle` subcommand, tar packaging, sigstore/timestamps (C6 follow-ons).
- Container isolation (C3 named follow-on).
- Localization, config files, shells other than the CLI itself.