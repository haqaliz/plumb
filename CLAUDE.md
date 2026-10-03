# Plumb: Project Context for Claude Code

This file orients a coding agent working in this repository. Read it first. Deeper context
lives in the `docs/` folder.

---

## What this project is

**Plumb** is an **execution-grounded research-integrity verifier**. Point it at a paper plus
the code and data behind it; Plumb re-runs the artifacts on the user's own compute, extracts
the paper's quantitative claims, binds each claim to a value it re-derived from the actual run,
and returns a **per-claim, reproducible verdict** — surfacing the claims that do *not* hold.

The name: a *plumb line* is the oldest tool for testing whether something stands true. "Plumb"
is also to investigate a thing to the bottom. Plumb asks of a paper: *does the claim hold when
you actually run it?*

Status: **the deterministic spine of C1, the C2 artifact-intake spine, the C3 run spine,
C4's binding & verdict, C5's first slices (store/bank/labels/metrics/report), and C6's
signed bundle are built; C7 and C8 are not.** `src/plumb/extract/`
holds the record layer (`ClaimValue`, `Location`, `Claim`, `StudyParameter`), a paper hash,
byte-identical serialization, value-identity dedup, Markdown table parsing, exhaustive candidate
extraction, and the admission gate that is the sole constructor of a `Claim`. One pinned
runtime dependency — pypdf (pure-Python, no transitive deps), powering the PDF→Markdown
converter in `src/plumb/pdf/`; no network reachable from any test.

**Not built:** C7, C8, C4/C6 beyond their first slices, and C5's second slice beyond `--bank`. **The `plumb verify` CLI is built** (2026-09-27): `src/plumb/cli/` is the
Phase 1 headline — `plumb verify <paper> <repo> [--rev REV] [--bindings FILE] [--out DIR]
[--from-record DIR] [--no-env-build] [--signer-key PATH] [--no-paper] [--json] [--bank]` runs the
C1→C2→C3→C4→C6 spine live (local dir / git URL with `--rev` / archive; real env build by
default, offline stub with `--no-env-build`) or replays a committed record (`--from-record`:
byte-identical re-derivation, cross-checked against the record's `verdicts.json`), renders a
fixed-layout verdict table or canonical JSON (byte-identical across invocations), writes a
signed bundle with `--out` that `verify_bundle` accepts, and banks the run into the
discrepancy corpus with `--bank` (2026-10-02: the live loop is closed; `corpus bank|report`
fold records in and pool coverage/precision/recall with denominators and label-authority
markers — the corpus holds case #1, AgroDesign 86/86 bound, 85 `REPRODUCED`, 1 `DIVERGED`,
precision/recall 1/1 `(owner)`). Exit 0 iff every claim decided; 1 on
any `UNVERIFIED` or named cause (`RECORD_INVALID`, `KEY_MISSING`, `BUNDLE_REFUSED`, ...); 2 on
usage; never a traceback, never `DIVERGED` on a harness failure. The AgroDesign record replays
through the CLI: 86 claims, 85 `REPRODUCED`, 1 `DIVERGED`, `--json` byte-identical to the
committed `verdicts.json`. **C4 binding & verdict, first slice, is
built** (2026-09-25): `src/plumb/verify/` takes C1 claims, a **user-written** bindings file
(no proposer) and a C3 run, locates exactly one value per claim through a JSON pointer, a
stdout regex or a CSV cell — read only through the object store by hash, never a stale
output — and decides it in pinned `Decimal` arithmetic: a `Point` against the paper's
**written precision** (`0.87` is `[0.865, 0.875]`) or an explicit tolerance, a `Bound` by its
operator. A run that wrote fewer digits than the paper is `ARTIFACT_PRECISION_COARSER`, never
`REPRODUCED`; all six value kinds compare (`Point`, `Bound`, `PlusMinus`, `Interval`,
`Range`, `Approximate` — `±`/CI/range/`~` included, D9–D13); percent claims must
declare a scale. Run causes govern every claim first, so **no harness failure can become
`DIVERGED`** — pinned by a mutation-checked guard — and every `DIVERGED` carries
`review_required`. Decisions D1–D8 in `docs/planning/binding-verdict/prd.md`. **C3 execution & capture is built** (2026-09-23): `src/plumb/run/`
resolves an entry point (explicit wins; else one `[project.scripts]` entry or a root
`main.py`; ambiguity or absence is a named cause, never a guess), runs it in a working copy of
the checkout under the run area (never the pinned checkout), and captures stdout/JSON/CSV into
a per-run object store keyed by SHA-256, folded into a deterministic `RunTrace`. The
**freshness guard** records any output older than the run start as `STALE_ARTIFACT` without
reading its bytes; `WONT_RUN`, `TIMEOUT`, `NO_ARTIFACT`, `ENTRYPOINT_MISSING`/`_AMBIGUOUS` are
the other named causes. Notebook capture is a named follow-on. **C2 artifact intake is built** (2026-09-22): `src/plumb/intake/`
resolves a local path, a git URL with `--rev`, or a tar.gz/zip archive into a pinned
`Checkout` with a recorded tree hash (`plumb` bytes framing over sorted `(relpath, bytes)`, or
the repo's own `HEAD^{tree}` for git sources, reconciled by the `scheme` field), scans
manifests, and describes the environment — lockfile-first → declared → best-effort dependency
policy, python pin (`.python-version` → `pyproject.toml` → default), isolation posture, and
`git`/`uv` tool versions. Resolution and description are offline-tested (`file://` repos,
synthetic archives, a stubbed env runner); the **one real `uv sync`** runs only via
`tools/demo_env_build.py` at dev time, never in tests or CI. Failures are named causes
(`SourceNotFound`, `RevNotFound`, `UnsupportedArchive`, `EnvBuildFailed`) — the future
`UNVERIFIED` input. **PDF input is built** (the `seam`, `columns`
and last-mile aspects, 2026-09-22): `extract_claims(pdf_to_markdown(pdf))` equals the
Markdown path by `Claim.id` at the recovery floor for **all five fixtures,
including the two-column journals** — PMC13134363 abstract 19/19 / whole-paper
non-table 19/19, PMC13298092 2/2 / 52/54 (0.963), PMC13363872 9/9 / 9/9
(1.000), PMC13332965 (vacuous abstract) / 38/41 (0.927), **PMC12780771
(Oxford) 6/6 / 25/25 (1.000)** — Oxford's former M4 exclusion (21/25, 0.840)
cleared on 2026-09-22: the M4 note's pypdf-CFF-font-gap hypothesis was tested
and **falsified** (fontTools changes nothing but pypdf's warning line, so it
was not added), and the real mechanisms — a publisher-split all-caps word,
table rows split at the column gutter, a surviving running-head page-number
fragment, and a separated citation numeral — were fixed deterministically in
the converter; rates, reasons and the falsification in
`fixtures/papers/README.md`. **Claim
*selection* — the substance of C1 — has
landed**: the M3 rule (`src/plumb/extract/selection.py`) scored pooled precision 1.0 / recall 1.0
on the 73-row blind set, floored at 0.90. Read that score honestly: it is *conformance*, not
validation — the labels were criteria-drafted from M3/M11 (owner-delegated pass), so a perfect
score means the rule implements its criteria. Validation against third-party labels is C5's job.
**The first real paper has run through the spine** (2026-09-26): AgroDesign, arXiv:2603.09041
(`fixtures/gate/agrodesign/`), on its own code at a pinned tag, through C2 → C3 → C4 — 86
rule-defined claims, **86 bound, 85 `REPRODUCED`, 1 `DIVERGED`** (a third-decimal Shapiro-Wilk
p, `review_required`, unchanged in an environment resolved as of the code's date). The
claims are curated by a fixed rule and grounded verbatim; **C1 recovered 0 of them when the gate
was met, and now recovers 86/86** (claim-recovery, 2026-09-27: §4's title reads as results,
`p ¡ 0.001` is refused, layout numerals are refused by name, and caption-led whitespace tables
name each cell by table, row and column — 86 claims, 86 distinct ids; no fixture claim moved). Two engine gaps it exposed were fixed test-first (`float_repr`
bindings for shortest-repr floats; `parse_trace`). The Phase 0 gate's **number exists**, and
**C6's first slice is built** (2026-09-27): `src/plumb/bundle/` writes a hash-listed directory
signed with `ssh-keygen -Y` (no crypto dependency; deterministic), and `verify_bundle` checks the
signature before reading anything, then the members, refused content (local paths, stderr), every
claim re-admitted against the paper **through the admission gate** (`readmit` — `parse_claims`
returns records, never a second door to `Claim`), and the re-derived verdicts, with named causes.
The AgroDesign bundle (`bundles/agrodesign/`) verifies, and `tools/bundle_replay.py` re-ran it
from a clean clone byte-identical. **The Phase 0 gate is met** (2026-09-27): the one
`DIVERGED` was reviewed by the owner and confirmed as a genuine reporting discrepancy. Met on one
paper — **cross-paper coverage (R1) is now measured (2026-10-02)**: the corpus holds 2
cases, 102 claims, 102 bound, 88 `REPRODUCED`, **14 `DIVERGED`** — AgroDesign (85/1) and
**Perrin, arXiv:2401.11842** (3/13: the paper's own code contradicts 13 of its 16 verified
Table 1 rates; all `review_required`, **owner-reviewed 2026-10-02: confirmed genuine**,
drift cross-check inconclusive by construction on this machine; precision/recall 14/14
`(owner)`). A fixed-rule panel search probed 4 candidates and found
1 additional runnable paper; evidence in `docs/planning/cross-paper-coverage/panel-run/screening.md`.
C1's 86/86 on AgroDesign remains conformance to a curated rule on one paper. Details:
`fixtures/gate/agrodesign/README.md`.

When in doubt, verify against the code and `git log` rather than this prose. Two assumptions in
these docs have already been falsified by real papers — the interval grammar required brackets no
paper writes, and a sign rule produced negative values no paper wrote — so treat the design
documents as intent, not as a description of behaviour.

Lineage: Plumb is a spin-out and generalization of a "reproduce & verify published work"
capability, lifted out of genomics and pointed at the literature at large. There is real, proven
design behind that idea, but Plumb is its own repo with its own guardrails.

---

## The wedge (read this before proposing any feature)

There are two things you could build. Know which one you are touching.

- **Guessing whether a claim is true.** An LLM reads the paper and opines "this looks wrong."
  CROWDED, unreliable, and not defensible — free AI tools measurably *cannot* do this reliably
  (JMIR 2026 found freely available AI tools cannot reliably flag even retracted literature).
  **We do NOT build this as the verdict.**
- **Re-deriving the claim from the paper's own artifacts and checking it by execution.** Run
  the repo, read the number it actually produces, compare it to the number the paper reports,
  on the user's data and compute. Essentially UNSOLVED at scale. **This IS the company.**

Frontier models hit only ~6.1% precision / ~21.1% recall on real errata-worthy errors (SPOT,
arXiv 2505.11855); only ~3.2% of published notebooks reproduce at all (a widely cited figure).
The execution/verification layer — not the guessing — is the moat.

---

## Key strategic constraints (do not violate)

1. **Execution decides, never a bare LLM judge.** A model may *extract* a candidate claim from
   the paper or *propose* how to bind it to an artifact. Only **re-execution against the real
   run** may produce a verdict. If a design lets a model's opinion stand in for a re-derived
   value, stop and flag it.
2. **No raw-data egress.** The paper, the repo, and the data run on the **user's compute**. Only
   hashes, metadata, and the verdicts the user chooses to publish ever leave the machine. Any
   LLM assist is **BYOK** (the user's own key) or a local model, disclosed, opt-in, off by
   default. Never send a paper or dataset to a cloud service the user did not authorize.
3. **Do not over-claim — this is the whole product.** `REPRODUCED` means the paper's number was
   re-derived within tolerance *from the paper's own artifacts*; it is **not** a claim the
   science is correct. `DIVERGED` is a discrepancy against the paper's own artifacts, **not** an
   accusation of misconduct. `UNVERIFIED` is never rendered as `REPRODUCED`. A discrepancy that
   could be our harness's fault (environment drift, a wrong binding) is `UNVERIFIED`, never
   `DIVERGED`.
4. **Build the part that gets BETTER as foundation models improve.** A stronger base model
   should extract cleaner claims and write better bindings, making Plumb sharper — never make
   the execution-grounded verdict redundant. Favor the deterministic spine (intake, run,
   re-derive, bundle) and the compounding discrepancy corpus over prompt tuning.
5. **Reproduce what ran, not what was committed.** A committed or stale output must never be
   read as a fresh result. A result whose file predates the run is `UNVERIFIED`, never parsed.
6. **Stay inside the founder's edge.** No wet-lab/clinical credentials, no proprietary datasets,
   no credential or model the founder lacks. The moat is engineering.
7. **Test-first.** Every capability lands with its failing test written first.

---

## The verdict contract (referenced throughout)

Per-claim, deliberately conservative. `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` /
`UNVERIFIED`, and **`UNVERIFIED` is never rendered as `REPRODUCED`.**

| Verdict | Meaning | May be emitted when |
|---|---|---|
| **REPRODUCED** | The paper's value was re-derived from its own run, within tolerance | The artifact ran, the value bound, and it matches |
| **WITHIN-TOLERANCE** | Matches within a stated numeric tolerance, not exactly | Same, with a non-zero delta inside the tolerance band |
| **DIVERGED** | The re-derived value contradicts the paper's claim | The artifact ran and its own output contradicts the paper — never on a harness-side failure |
| **UNVERIFIED** | We could not decide | Repo won't run, claim won't bind, result is stale, tolerance can't be set, or a model-only signal — the honest default |

A model may write or propose a check; **execution** assigns the verdict. Any failure to
evaluate resolves to `UNVERIFIED` with a named cause — never a silent pass, never `DIVERGED` by
default.

---

## Tech direction

- **Agentic system**: an orchestrator that intakes a paper + repo, builds a pinned environment,
  runs the artifacts, isolates failures, and re-derives + compares each claim. Failure recovery
  and reproducibility are first-class.
- **Python core** (via `uv`), CLI-first (`plumb`), self-hostable OSS engine; a hosted layer
  comes later. Exact stack details live in `docs/technical/ARCHITECTURE.md` — check it before
  assuming.
- Pinned versions, deterministic artifacts, content-addressed traces, and a signed replayable
  bundle are core requirements, not nice-to-haves.
- Capture every (claim, re-derived value, verdict) into the discrepancy corpus wherever
  feasible: it is the compounding evaluation dataset and part of the moat.

---

## Founder profile

Solo / small team. **Full-stack developer + ML engineer + genetics passion.** No wet-lab or
clinical credentials, by design: the moat is engineering. Optimize for an
engineering-defensible product.

---

## Folder / docs structure

```
README.md                          # Repo front door
VISION.md                          # Narrative thesis, moat, non-goals
CLAUDE.md                          # This file
docs/
  ROADMAP.md                       # Phased plan + risk register
  technical/CAPABILITY_ROADMAP.md  # C1..C8 engine capabilities in build order
  technical/ARCHITECTURE.md        # Design: intake → run → re-derive → verdict → bundle
  planning/{slug}/                 # In-flight PRDs, specs, and plans (per unit of work)
```

Consult the relevant file before non-trivial decisions, and keep docs in sync when direction
changes.

---

## Quick facts for grounding (do not fabricate beyond these)

- Frontier models: ~6.1% precision / ~21.1% recall on real errata-worthy errors (SPOT,
  arXiv 2505.11855).
- ~3.2% of published computational notebooks reproduce (widely cited; verify before quoting a
  precise denominator).
- Free AI tools cannot reliably flag even retracted literature (JMIR 2026).
- Retractions passed ~10,000/year (2023); publishers now pay for submission-screening
  (Elsevier Check Integrity across ~2,000 journals, Mar 2026; Springer Nature automated checks;
  STM Integrity Hub).

If you need a statistic that isn't here, do not invent one; say it's unverified.

## graphify

If a `graphify-out/` directory ever appears in this repo, treat codebase/architecture/
file-relationship questions as graphify queries first (`graphify query`, `graphify explain`,
`graphify path`; graph at `graphify-out/graph.json`) before grep/read, per the global CLAUDE.md.
