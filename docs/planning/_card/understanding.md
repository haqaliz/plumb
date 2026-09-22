# C3 Execution & result capture — understanding (deep dig, 2026-09-22)

## What the work is really asking

The Phase 0 gate's C3 minimum: "run the repo's own entry point and capture structured output,
freshness-guarded" (`docs/ROADMAP.md:23`). C2 (this branch's parent) provides
`Checkout(checkout_dir, tree_hash, source_record)` and `EnvDescriptor`/`build_environment`
(`src/plumb/intake/`). C3 consumes them: run the paper's code, capture what it produced,
hash it, and refuse to ever read a stale artifact as a fresh result (constraint #5 — "Reproduce
what ran, not what was committed").

## Design contract (ARCHITECTURE.md:84-91, verified against docs and the C2 code)

- **Run** the repo's own entry point(s) under the recorded environment (subprocess, cwd =
  checkout, scrubbed env, timeout — C2's posture).
- **Capture** structured outputs: JSON, CSV, stdout — each **content-addressed** by hash.
- **Freshness guard:** an output whose provenance/mtime predates this run is `STALE_ARTIFACT`
  (`UNVERIFIED` cause at verdict time), **never parsed**.
- **Failures:** won't build, won't run, times out → captured with a named cause, never silent.
- Notebook cell outputs are in the capability text but depend on nbconvert; defer (out of
  scope, named follow-on).

## Conventions that must be preserved (verified)

- No network in tests (autouse blocker, `tests/conftest.py:56-60`); `subprocess` legal —
  tests run `python -c "..."` and small script fixtures.
- `src/plumb/run/` is outside the extract/ AST-guard scope — `os`, `pathlib`, `time`,
  `subprocess`, `hashlib` are usable (freshness needs `os.stat().st_mtime`).
- Determinism: content-addressed outputs (sha256) are stable; the RunTrace record is
  deterministic (no absolute tmp paths in the *record* — record relpaths; or pin the scheme).
- Test-first (constraint #7). Named causes → future `UNVERIFIED` mapping, never silent.
- C2's `EnvBuildFailed` maps to a future `UNVERIFIED`; C3 adds run-side causes.

## Open questions the PRD must settle

1. **Entry-point discovery:** explicit entry point (passed in / default) vs discovery from
   `scan_manifests` (pyproject scripts, `main.py`). First slice: explicit with a recorded
   default-discovered choice (e.g. `main.py` → `python main.py`; pyproject script group →
   `uv run <script>`), the exact argv recorded in the trace. Ambiguity → named cause
   `ENTRYPOINT_AMBIGUOUS` rather than guessing.
2. **Artifact discovery:** which files produced by the run count as outputs — any
   `.json`/`.csv` created under the run area during the run, plus stdout. Everything is
   hashed; the trace links run → artifact hashes. Pre-existing committed outputs in the
   checkout are never captured unless the run writes them (that IS the freshness guard).
3. **Freshness semantics:** artifact mtime must be ≥ run start; `mtime < run_start` →
   `STALE_ARTIFACT` (never parsed). Back-dating in tests exercises it. Also: outputs written
   to the checkout dir vs a dedicated run dir — run dir preferred (scratch), so committed
   files can't be accidentally captured.
4. **Notebooks:** out of scope (needs nbconvert); recorded follow-on.
5. **Timeout & resource caps:** recorded defaults (e.g. 1800s like C2), documented.