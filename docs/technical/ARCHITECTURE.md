# Plumb Architecture

The engine design: **intake → run → re-derive → verdict → bundle.** This is the authoritative
technical reference once code exists; today it is the design of record. Strategic framing is in
[`../../VISION.md`](../../VISION.md) and [`../../CLAUDE.md`](../../CLAUDE.md); the capability
sequence is in [`CAPABILITY_ROADMAP.md`](CAPABILITY_ROADMAP.md).

The load-bearing rule, restated because every component depends on it: **a model may extract a
claim or propose a binding; only execution assigns a verdict.** No component may promote a
result to `REPRODUCED` on a model's opinion, and no failure may silently pass.

---

## The pipeline

```
paper (text/PDF/DOI)                 repo/data (path | git URL --rev)
        │                                    │
        ▼                                    ▼
  ┌───────────┐                       ┌──────────────┐
  │ C1 Extract│                       │ C2 Intake &  │
  │  claims   │                       │  pinned env  │
  └─────┬─────┘                       └──────┬───────┘
        │ typed claims                       │ pinned checkout + env
        │                                    ▼
        │                            ┌──────────────┐
        │                            │ C3 Execute & │
        │                            │ capture      │  (freshness-guarded,
        │                            └──────┬───────┘   content-addressed)
        │                                   │ re-derived values
        └──────────────┬────────────────────┘
                       ▼
                ┌──────────────┐
                │ C4 Bind &    │  locator → compare(tolerance)
                │  re-derive   │  → REPRODUCED / WITHIN-TOLERANCE
                │   verdict    │    / DIVERGED / UNVERIFIED
                └──────┬───────┘
                       ├────────────► C5 Discrepancy corpus (bank every case)
                       ▼
                ┌──────────────┐
                │ C6 Signed    │  replayable: paper hash + tree hash
                │  bundle      │  + env + traces + verdicts
                └──────────────┘
```

`C7` (no-code internal-consistency) is a parallel path off `C1` for papers with no runnable
artifacts. `C8` (hosted layer) wraps the whole pipeline as a managed, BYOK service.

---

## Components

### C1 — Claim extractor (`src/plumb/extract/`)

- **Input:** paper as text, Markdown, PDF (→ text), or a DOI the user resolves locally.
- **Output:** a list of typed `Claim` records — reported value, units, the **metric** it
  measures, tolerance hint, a citation location in the paper, the artifact/table/figure it should
  be derivable from, and a derived **`id`**. Plus `StudyParameter` records (reported N and
  similar), which are **not** claims.
  - The **`metric`** is required: C4 aims a locator at a *named quantity*, and without it the
    binder would have to re-interpret prose at bind time.
  - The **`id`** is derived from `(reported value text, metric, units)` and **excludes
    `location`**, so that merging duplicate mentions of one result does not change identity.
  - The reported value keeps the paper's **verbatim text** alongside a `Decimal`. Note
    `Decimal("0.870") == Decimal("0.87")` is `True`, so value identity is keyed on the text;
    keying it on the `Decimal` would silently merge two values a paper stated differently.
  - There is **no `confidence` field**, by construction — a confidence score becomes
    `if confidence > 0.9` at verdict time, which is a model's opinion standing in for a
    re-derived value (constraint #1).
- **Deterministic core** parses numbers, tables, and reported statistics. An **optional BYOK
  LLM proposer** (off by default) suggests additional candidate claims; every proposed claim is
  re-grounded deterministically against the paper text before admission. The proposer never
  emits a verdict and never sees the verdict path.

### C2 — Artifact intake & environment (`src/plumb/intake/`)

- Resolve a **local path**, an `https` **git URL** with `--rev`, or an archive into a pinned
  checkout; record the **tree hash**.
- Build a reproducible environment on the **user's compute** (pinned interpreter + deps;
  lockfile-first, then declared deps, then a best-effort resolve that is recorded as such).
- Nothing is uploaded. An LLM assist, if enabled, is BYOK. Untrusted repo code runs under the
  user's chosen isolation (documented; the isolation posture is recorded in the bundle).
- **Status (2026-09-22):** the deterministic intake spine is built — tree hashing (plumb bytes
  framing over sorted `(relpath, bytes)`, and the repo's own `HEAD^{tree}` for git sources,
  reconciled by the `scheme` field), source resolution (`resolve_local` / `resolve_git` /
  `resolve_archive` → `Checkout`), manifest scan, and the environment descriptor
  (`describe_environment`: lockfile-first → declared → best-effort policy, python pin, isolation
  posture, tool versions). Resolution is offline-tested (`file://` repos, synthetic archives);
  the **one** real `uv sync` runs only via `tools/demo_env_build.py` at dev time, never in
  tests or CI. The named causes (`SourceNotFound`, `RevNotFound`, `UnsupportedArchive`,
  `EnvBuildFailed`) are the future `UNVERIFIED` input. The env builder (real pinned environment
  on untrusted code) beyond that dev-time sync is not yet built.

### C3 — Execution & result capture (`src/plumb/run/`)

- Run the repo's own entry point(s); capture **structured outputs** (JSON, CSV, stdout,
  notebook cell outputs), each **content-addressed** by hash.
- **Freshness guard:** an output whose provenance/mtime predates this run is never read as a
  fresh result — it yields `UNVERIFIED` with cause `STALE_ARTIFACT`, never a parsed value.
- Failures (won't build, won't run, times out) are captured with a named cause, never silently
  dropped.
- **Status (2026-09-23):** the run spine is built — `resolve_entrypoint` → `run_entrypoint` →
  `capture_outputs` → `build_trace` (`run_and_capture` chains the last three). The run works
  in a copy of the checkout under its run area (mtimes preserved, so a committed output stays
  older than the run start), never in the pinned checkout. Fresh outputs go into a per-run
  object store keyed by SHA-256 and are read back only by hash; a stale output is recorded
  without its bytes ever being read. Causes: `ENTRYPOINT_MISSING`, `ENTRYPOINT_AMBIGUOUS`,
  `ENV_BUILD_FAILED` (C2), `WONT_RUN`, `TIMEOUT`, `STALE_ARTIFACT`, `NO_ARTIFACT` — mapping
  table in `src/plumb/run/__init__.py`. Notebook cell capture is a named follow-on.

### C4 — Binding & verdict (`src/plumb/verify/`) — the moat

- **Locators** bind a `Claim` to a captured value: JSON pointer, table cell reference,
  regex/stdout capture, notebook cell index. A model may *propose* a locator; the bind and the
  compare are executed by code.
- **Compare** within a stated tolerance and emit the verdict:

  | Verdict | Condition |
  |---|---|
  | `REPRODUCED` | bound, ran, matches exactly (or tolerance is zero and delta is zero) |
  | `WITHIN-TOLERANCE` | bound, ran, delta non-zero but inside the tolerance band |
  | `DIVERGED` | bound, ran, and the artifact's own output contradicts the paper's claim |
  | `UNVERIFIED` | anything else, with a named cause (see below) |

- **`UNVERIFIED` causes** (closed, extensible vocabulary): `NO_ARTIFACT`, `WONT_RUN`,
  `NO_BINDING`, `AMBIGUOUS_BINDING`, `NO_TOLERANCE`, `STALE_ARTIFACT`, `PROPOSER_UNGROUNDED`,
  `MODEL_ONLY_SIGNAL`. Any failure to decide resolves here — never `DIVERGED` by default, never
  a silent `REPRODUCED`.
- **`DIVERGED` is conservative by construction:** it requires the artifact's *own* run to
  contradict its *own* claim. A discrepancy attributable to harness fault (env drift, wrong
  locator) is `UNVERIFIED`, not `DIVERGED`.

### C5 — Discrepancy corpus (`src/plumb/corpus/`)

- Every `(claim, re-derived value, verdict, locator, cause)` is banked as a self-contained,
  replayable, human-labelable case under gitignored `corpus/local/`.
- Precision/recall/coverage are measured against human labels; `UNVERIFIED` is excluded from
  precision, and the engine never labels its own cases. This is the calibration instrument and
  moat #2.

### C6 — Signed bundle (`src/plumb/bundle/`)

- A signed record binding paper hash + repo tree hash + environment descriptor + run traces +
  per-claim verdicts, such that a third party can **replay** and reach the same verdicts.
- Only what the user chooses to publish is included — hashes, verdicts, and the method, not raw
  data (constraint #2).

### C7 — Internal-consistency checks (`src/plumb/consistency/`)

- statcheck/GRIM-style internal-numeric-consistency checks for PDF-only papers.
- Emits an **internal-inconsistency** signal, explicitly labeled weaker than a re-executed
  verdict; never rendered as a ground-truth `DIVERGED`.

### C8 — Hosted layer (out of the OSS core)

- Wraps the pipeline as a managed, BYOK, opt-in service. Out of scope until C4's precision is
  defensible and C5 has teeth. No raw-data egress beyond what the customer authorizes.

---

## Cross-cutting decisions

- **Language/runtime:** Python core via `uv`, CLI-first (`plumb`). First target corpus is
  Python/R data-analysis papers that run. (Matches the founder's engine work and the sibling
  projects.)
- **Determinism & provenance:** pinned versions, content-addressed artifacts, recorded
  environment. A verdict must be re-derivable from the bundle alone.
- **Privacy:** runs on the user's compute; BYOK for any LLM assist; only chosen
  hashes/verdicts/method leave the machine.
- **CLI shape (target):** `plumb verify <paper> <repo> [--rev REV] [--tolerance ...]
  [--propose-claims] [--out bundle/]` → per-claim verdict table + `UNVERIFIED`-with-cause +
  signed bundle. `--propose-claims` (BYOK) is the only path that engages an LLM and is off by
  default.
- **Testing:** test-first; no network in CI; determinism pinned by tests; every `UNVERIFIED`
  cause has a test; the freshness guard and the false-`DIVERGED` guard are load-bearing tests.

---

## Open questions (resolve as code lands)

- Signing scheme for the C6 bundle (sigstore-style vs a simpler detached signature).
- Isolation default for running untrusted repo code (container vs lighter sandbox). **First
  slice (decided 2026-09-22):** a subprocess on the user's compute with a scrubbed env (secret-
  bearing variables removed), cwd = checkout, a timeout, and no network beyond the recorded env
  build itself (pull-only) — recorded verbatim in the env descriptor (`src/plumb/intake/env.py`).
  C3 (2026-09-23) refines "cwd = checkout" to cwd = a working copy of the checkout under the
  run area, so a run can never write into the pinned tree (or, for a local source, the user's
  own directory); it also sets `UV_OFFLINE=1` and kills the whole process group on timeout.
  Container isolation is a named follow-on; whatever lands, the posture is recorded in the
  bundle regardless.
- Tolerance policy: per-claim explicit vs a typed default per claim kind; how to represent "no
  defensible tolerance" (→ `UNVERIFIED: NO_TOLERANCE`).
- Locator grammar: how much a model may propose vs a fixed deterministic set.
- Value identity across spellings: `0.87`, `.87` and `0.870` are currently three identities,
  because identity is the verbatim text. That errs toward splitting (visible in the coverage
  number) over merging (silently loses a claim), but a paper writing `.87` in a table and `0.87`
  in its abstract double-counts one result. Any canonical form adopted for identity must be used
  for identity *only*, never for comparison.
- Whether hyphen-separated ranges (`12-15`) should parse. Today only en/em dashes do, since an
  ASCII hyphen is ambiguous against a signed or subtracted value — a known recall gap, left to be
  measured against labelled papers rather than guessed at.

These do not block C1–C3; they must be settled before C4's verdict is published as a finding.
