# C2 Artifact intake — understanding (deep dig, 2026-09-22)

## What the work is really asking

The Phase 0 gate needs "C2 (minimum): resolve a local path or git URL to a pinned checkout on
the user's compute" (`docs/ROADMAP.md:22`). Nothing under `src/plumb/` exists beyond
`extract/` and `pdf/`; `src/plumb/intake/` does not exist (the ARCHITECTURE.md diagram names
it at `:75`). This unit builds it: source resolution → pinned checkout + recorded tree hash →
reproducible environment descriptor (+ runner), with the isolation posture recorded.

## Design contract (ARCHITECTURE.md:75-82, verified against the docs)

- **Sources:** local path | `https` git URL with `--rev` | archive (`.tar.gz`/`.zip` today).
- **Pinned checkout:** tree hash recorded. For git sources the repo's own tree object
  (`HEAD^{tree}`) is the natural content address; for non-git sources (local dir, archive) a
  deterministic plumb tree hash over sorted `(relpath, bytes)` — **no mtimes, no order
  dependence**, so the hash is stable across checkouts and machines.
- **Environment:** pinned interpreter + deps; **lockfile-first** (e.g. `uv.lock` +
  `pyproject.toml` → `uv sync`), then **declared deps** (requirements files), then
  **best-effort resolve recorded as such**. The build runs on the user's compute; the
  descriptor is what gets recorded (and later bundled in C6).
- **Isolation posture:** documented and recorded; container is an open question
  (`ARCHITECTURE.md:164-166`). First slice: subprocess with scrubbed env, cwd = checkout,
  timeout, no network unless the user's env build requires it (env build is pull-only, never
  egress of user data — R5).
- **Nothing uploaded** (constraint #2); the git/archive fetch is pull-only and authorized.

## Conventions that must be preserved (from the C1/C1-pdf work, verified)

- **No network in tests:** autouse `_block_network` (`tests/conftest.py:56-60`) blocks
  sockets; `subprocess` is deliberately NOT blocked (documented gap, `conftest.py:17-18`) —
  so `git clone file://...` and running scripts in tests is legal, but any real network fetch
  is not.
- **Determinism suite** (`tests/extract/test_determinism.py`) AST-scans only
  `src/plumb/extract/` — `src/plumb/intake/` is outside its scope, so `os`/`pathlib`/`time`
  are usable there (unlike extract/). Intake still gets its own no-network + determinism
  tests (tree hash stable across runs and processes; hash input = sorted bytes only).
- **Test-first** (constraint #7): every aspect's first commit is its failing test.
- **No over-claim:** the env builder's offline tests cover descriptor logic; the real
  `uv sync` is a dev-time demo (documented), because CI must not reach the network.
- Freshness/provenance (constraint #5) belongs to C3, but the intake record (checkout path +
  tree hash + source) is what C3's freshness guard compares against.

## Open questions the PRD must settle

1. **Isolation posture for the first slice** — subprocess + scrubbed env + timeout (recorded
   in the descriptor), container deferred; or a container default if docker exists? The docs
   leave it open; the first slice should pick the lighter posture and record it.
2. **Git vs non-git tree identity** — use `HEAD^{tree}` for git sources and a plumb tree hash
   for local/archive; two schemes must be reconciled in one `TreeHash` record (scheme field).
3. **Entry-point discovery** belongs to C3; intake only records "what a repo looks like"
   (manifests present: `uv.lock`, `pyproject.toml`, `requirements*.txt`, `environment.yml`,
   `Makefile`, `main.py`) so C3 can pick entry points.
4. **Archive handling** — tar/zip extraction is stdlib (`tarfile`/`zipfile`); no new deps.
5. **Dependency policy** — intake adds no runtime deps (stdlib + subprocess git/uv).