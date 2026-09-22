# PRD — C2 artifact intake & pinned environment (slug: `artifact-intake`)

## Problem Statement

The Phase 0 gate's C2 minimum is "resolve a local path or git URL to a pinned checkout on the
user's compute" (`docs/ROADMAP.md:22`). Nothing can be re-run reproducibly without a pinned,
rebuildable checkout and environment: R1 (binding coverage, High/High) is mitigated by
multiple locator types *and* by the run side actually working, which starts here. C2 is the
first unshipped capability (`docs/technical/CAPABILITY_ROADMAP.md:51-60`); C1 is complete on
the `c1-pdf-input` branch.

## Goals & Success Metrics

Resolve a local path, an `https` git URL with `--rev`, or an archive into a pinned checkout
with a recorded tree hash, and produce a reproducible environment descriptor (lockfile-first →
declared deps → best-effort recorded), with the isolation posture recorded. Everything stays
on the user's compute (constraint #2).

### Acceptance criteria (test-first)

1. All three source types resolve to a pinned checkout with a stable tree hash, deterministically and offline in tests (`file://` git repos, synthetic tar/zip archives, local dirs).
2. Tree hash is stable across runs and processes; input is sorted `(relpath, bytes)` only — no mtimes, no order dependence.
3. Git sources record the repo's own tree object (`HEAD^{tree}`) with the scheme named; non-git sources use the plumb tree hash — one `TreeHash(scheme, digest)` record type.
4. Environment descriptor picks lockfile-first when a lockfile exists, declared deps next, best-effort-resolve last — and **records which policy was used** (never silent).
5. Isolation posture is a recorded field in the descriptor (subprocess + scrubbed env + timeout; container deferred).
6. No network in any test (autouse blocker stays green; `git clone file://` and script runs via subprocess are legal); no new runtime dependencies (stdlib + git/uv subprocess).
7. Failures resolve to named causes (`SourceNotFound`, `RevNotFound`, `UnsupportedArchive`, `EnvBuildFailed`, ...) — never silent drops; the future C4 layer maps these to `UNVERIFIED` causes.

## User Personas & Scenarios

- **The gate:** `plumb verify <paper> <repo>`'s repo side — a local path or git URL resolves to a pinned checkout on the user's compute.
- **A researcher re-running a paper:** points Plumb at a repo; gets a pinned, rebuildable environment; can replay later.
- **Internal:** C3 consumes the checkout + env descriptor; C6 bundles the descriptor + tree hash.

## Requirements

### Must-have

- **M1. Source resolution.** `resolve_local(path)`, `resolve_git(url, rev)` (clone to a
  workdir under the run area, checkout `rev`), `resolve_archive(path)` (tar/zip, stdlib),
  each producing a `Checkout(checkout_dir, tree_hash, source_record)`.
- **M2. Tree hashing.** `plumb_tree_hash(dir)` — SHA-256 over sorted `(relpath, bytes)`,
  `.git` excluded; `TreeHash(scheme: "git-tree" | "plumb", digest: str)`.
- **M3. Env descriptor.** `describe_environment(checkout) -> EnvDescriptor` — python pin
  (from `.python-version`/`pyproject`/default), dependency policy detection (lockfile-first →
  declared → best-effort), policy recorded; tool versions recorded at resolve time (`git
  --version`, `uv --version`); `build_environment(checkout, descriptor) -> EnvBuild` — runner
  seam that executes the recorded policy on the user's compute; in tests the runner is a stub
  (offline), the real `uv sync` runs only via the recorded dev-time demo script
  (`tools/demo_env_build.py`, output committed as evidence in the PR) — the descriptor is
  bundle-able by C6 regardless of whether the build succeeds.
- **M4. Isolation posture.** Recorded field: subprocess, scrubbed env (no secrets), cwd =
  checkout, timeout; posture string lands in the descriptor for C6.
- **M5. Manifest scan.** `scan_manifests(checkout)` — which manifests exist (`uv.lock`,
  `pyproject.toml`, `requirements*.txt`, `environment.yml`, `Makefile`, `main.py`) — for C3's
  entry-point discovery.
- **M6. Docs.** `ARCHITECTURE.md` open-question note updated (isolation posture decided for
  the first slice); `CAPABILITY_ROADMAP.md` C2 status moved from "not built"; `README.md`/
  `CLAUDE.md` status rows updated — honestly, without claiming the gate.

### Should-have

- **S1.** Re-resolution: resolving the same source twice yields the same tree hash (idempotence test).
- **S2.** Named causes documented as the future `UNVERIFIED` mapping table (in the module docstring).

### Nice-to-have

- **N1.** `--rev` defaulting to the repo's default branch when absent, recorded as such.

## Technical Considerations

- **Capability:** C2 (`CAPABILITY_ROADMAP.md:51-60`). Depends on nothing; C3 depends on it.
- **Package:** `src/plumb/intake/` — outside the extract/ AST-guard scope; `os`, `pathlib`,
  `hashlib`, `tarfile`, `zipfile`, `subprocess` allowed; own no-network + determinism tests.
- **Determinism:** tree hash input is sorted bytes; no mtimes; git tree object for git
  sources. Cross-process stability test (subprocess pattern).
- **No-network in tests:** `file://` git repos created in tmp dirs; archives synthesized in
  tests; the env runner is a stub in tests.
- **Verdict impact:** none directly — intake produces records, never verdicts. Its named
  failure causes are the future `UNVERIFIED` input (documented in M6/S2).
- **No new runtime deps** (stdlib + subprocess git/uv). Git and uv must exist on the user's
  machine; recorded as external tools in the descriptor.

## Risks & Open Questions

- **R1 (binding coverage)** — the mitigation this unit starts; the run side must actually
  work on real repos, which C3/C4 will prove. Honest boundary: tests exercise resolution
  offline; the real `uv sync` is dev-time until CI can host a cache.
- **Env build is the one network-touching step** — pull-only, authorized, on the user's
  compute (R5: never egress). Documented in the descriptor posture.
- **Open:** whether `HEAD^{tree}` vs plumb-tree-hash divergence matters downstream — C6
  bundles whichever scheme the source used; replay uses the same scheme. No migration needed.
- **Open:** archive bomb / huge checkout limits — first slice: size cap recorded (default
  generous), documented, **enforcement deferred as a named follow-on** (not ambiguous).

## Out of Scope

- Entry-point discovery and execution (C3), freshness guard (C3), verdicts (C4), bundle
  signing (C6), container isolation, notebook environments, DOI resolution.

## Proposed Aspect Decomposition

1. `checkout` — resolution (local/git/archive) + tree hashing + `TreeHash` record; offline
   tests with `file://` repos and synthetic archives.
2. `environment` — manifest scan, env descriptor policy selection, posture record, runner
   seam with offline stub; dev-time demo documented.
3. `seam` — public API surface (`intake.resolve_*`, `intake.describe_*`), failure-cause
   vocabulary, doc amendments (M6/S2).

Sequencing: `checkout` → `environment` → `seam`.