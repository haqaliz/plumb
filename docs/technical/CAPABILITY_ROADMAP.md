# Plumb Capability Roadmap (C1..C8)

The engine as a set of capabilities in build order. This is the primary candidate set for
`plumb-next`. Each entry states what it does, why it matters, its dependencies, and its guardrail
tie-in. Phasing lives in [`../ROADMAP.md`](../ROADMAP.md); the design in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

**The moat is C4.** C1–C3 feed it; C5–C6 compound and prove it; C7 extends it to no-code papers;
C8 sells it. Do not let effort drift into anything that a stronger base model would make
redundant (see CLAUDE.md constraint #4).

Verdict vocabulary used throughout: `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` /
`UNVERIFIED`. A model may extract or propose; **execution decides**.

---

## C1. Paper-claim extraction

**What:** take a paper (text, Markdown, PDF, or DOI → text) and produce a set of typed
**quantitative claims** — each with the reported value, units, the metric it measures, location in
the paper, and the artifact it should be derivable from. Reported study parameters (notably N) are
extracted alongside as a **separate record type**, not as claims.

**Why:** you can't verify what you haven't pinned down. The claim is the unit of work.

**Design:** deterministic core (numeric/table/stat parsing) + an **optional BYOK LLM proposer**
that suggests candidate claims. Every LLM-proposed claim is deterministically re-grounded against
the paper text before it is admitted. The proposer never assigns a verdict.

**Depends on:** nothing. **Guardrail:** constraints #1, #3 — a candidate the paper doesn't
actually make never becomes a `Claim`, and is never carried forward as `DIVERGED`. It is recorded
as a **non-claim with a named cause** rather than discarded silently: an invisible drop is
indistinguishable from a claim that was never there, and it flatters the coverage number the
Phase 0 gate rests on (`ARCHITECTURE.md` "never a silent pass"; `ROADMAP.md` R3).

**Status (2026-09-21, seam 2026-09-22, last-mile 2026-09-22):** the deterministic spine of C1 has landed under
`src/plumb/extract/` —
the record layer (`ClaimValue`, `Location`, `Claim`, `StudyParameter`), a content hash over
normalized paper text, byte-identical serialization pinned by cross-process tests, and
value-identity dedup. One pinned runtime dependency — pypdf (pure-Python, no transitive deps),
powering the PDF→Markdown converter in `src/plumb/pdf/`; no network reachable from any test.
The `pdf-input` slice landed test-first through the sealed `extract_claims(raw)` seam
(`src/plumb/extract/pipeline.py:29-61`): claim-id recovery of the PDF path vs the Markdown
path is measured per fixture (`tests/extract/test_pdf_seam.py`). **All five
fixtures clear both recovery floors** (abstract 100%, whole-paper non-table ≥ 0.90, the
survey-set floor) — PMC13134363 19/19 · 19/19 (1.000), PMC13298092 2/2 · 52/54 (0.963),
PMC13363872 9/9 · 9/9 (1.000), PMC13332965 (vacuous abstract) · 38/41 (0.927),
**PMC12780771 (Oxford) 6/6 · 25/25 (1.000)** — including the
**two-column journals** (the `columns` aspect, 2026-09-22: text-matrix direction,
gutter detection, column grouping, furniture drops) and the last-mile fixes
(2026-09-22): table-structure lines stay whole at the gutter, the running-head
page-number fragment drops as furniture, the citation numeral glues, and a
publisher-split all-caps word is rejoined when the paper writes it whole
elsewhere. Oxford's former M4 exclusion (21/25, 0.840) is cleared; its M4 note's
pypdf-CFF-font-gap hypothesis was tested and **falsified** — fontTools changes
nothing but pypdf's warning line, so it was not added and pypdf remains the one
pinned dependency; the full account is in `fixtures/papers/README.md`.

**Not built:** C5–C8 (C2's intake spine, C3's run spine and C4's first slice have landed — see C2–C4 below). **Selection — the substance of this
capability — has landed** (aspect 2 part 2, 2026-09-21): the M3 rule under
`src/plumb/extract/selection.py` with a closed selection-side cause vocabulary, a free-text
metric namer, `extract_claims(raw)` as the end-to-end seam, and pooled precision/recall over
the 73-row blind set — **1.0 / 1.0, floored at 0.90**. The score is a *conformance* score, not
validation: the labels were criteria-drafted from M3/M11 (the owner delegated the pass), so a
perfect score means the rule implements its criteria. Validation against third-party labels is
C5's job. The Phase 0 gate's **C1 prerequisite ("text/PDF") is met for the fixtures as a
whole** — all 5/5 fixtures clear the recovery floors, including the two-column journals
(Oxford cleared its M4 exclusion at 25/25 non-table, 1.000, on 2026-09-22; the full
mechanism account is in `fixtures/papers/README.md`). The
gate itself still needs a real paper run through C4 (C2's minimum — resolve a local path or git
URL to a pinned checkout — is met as of 2026-09-22; C3's — run the repo's own entry point and
capture structured output, freshness-guarded — as of 2026-09-23; C4's first slice binds and
decides on synthetic repos as of 2026-09-25), so **the gate is not met and C1 must not be read
as complete.**

## C2. Artifact intake & pinned environment

**What:** resolve the code/data behind the paper — a local path, an `https` git URL with
`--rev`, an archive — into a **pinned checkout** (tree hash recorded) and build a reproducible
environment on the **user's compute**.

**Why:** reproducibility is impossible without a pinned, rebuildable environment.

**Depends on:** nothing. **Guardrail:** constraint #2 — everything stays local; nothing is
fetched to a third party the user didn't authorize.

**Status (2026-09-22):** the deterministic intake spine is built under `src/plumb/intake/` —
tree hashing (a `plumb` bytes framing over sorted `(relpath, bytes)`, and the repo's own
`HEAD^{tree}` for git sources, one `TreeHash(scheme, digest)` record), source resolution
(`resolve_local` / `resolve_git` with `--rev` / `resolve_archive` → `Checkout(checkout_dir,
tree_hash, source_record)`), manifest scan, and the environment descriptor (`describe_environment`
with a lockfile-first → declared → best-effort policy, python pin from `.python-version` →
`pyproject.toml` → default, isolation posture, and `git`/`uv` tool versions). Named causes
(`SourceNotFound`, `RevNotFound`, `UnsupportedArchive`, `EnvBuildFailed`) map to the future
`UNVERIFIED` causes. The boundary is honest: resolution and the descriptor are **offline-tested**
(`file://` repos, synthetic tar/zip archives, stub env runner), while the **one real `uv sync`**
runs only via `tools/demo_env_build.py` at dev time (its output is recorded as evidence in the
PR, not in CI). C3 consumes this checkout + descriptor (built 2026-09-23, see below); C4's
first slice consumes C3 (2026-09-25), but **no real paper has run through it, so the Phase 0
gate is not met.**

## C3. Execution & result capture

**What:** run the repo's own entry point(s) and capture structured outputs — JSON, CSV, stdout,
notebook cell outputs — **content-addressed** and **freshness-guarded** (an output file whose
mtime/provenance predates this run is never read as a fresh result).

**Why:** the re-derived value must come from an actual run, not a committed artifact.

**Depends on:** C2. **Guardrail:** constraint #5 — reproduce what ran, not what was committed.

**Status (2026-09-23):** the run spine is built under `src/plumb/run/` — entry-point
resolution (explicit argv wins; else exactly one of a single `[project.scripts]` entry → `uv
run <name>` or a root `main.py` → `python main.py`; more is `ENTRYPOINT_AMBIGUOUS`, none is
`ENTRYPOINT_MISSING` — never a guess), the runner (`run_entrypoint`: a subprocess in a
**working copy of the checkout** under the run area — mtimes preserved, `.git`/`.venv` not
copied, the pinned checkout never touched — with C2's scrubbed env, `UV_OFFLINE=1`, a built
`.venv` used in place, and a timeout that kills the whole process group; `WONT_RUN` and
`TIMEOUT` recorded), capture (`capture_outputs`: stdout, stderr and every `.json`/`.csv`
hashed into a per-run object store, read back only by hash; stderr diagnostic-only), and the
deterministic `RunTrace` (`run_id` = SHA-256 over argv + tree hash + sorted locatable artifact
hashes; canonical JSON, no run-side absolute paths, byte-identical across processes). **The
freshness guard is load-bearing:** an output whose mtime is strictly before the run start is a
`STALE_ARTIFACT` record whose bytes are never read — an untouched committed output, a
back-dated file and a `cp -p` of a committed result are all caught, and a mutation check
(guard removed, or loosened to `<=`) fails the suite. A successful run with no fresh output and
empty stdout is `NO_ARTIFACT`. All offline-tested with local programs. **Not built:** notebook
cell capture (needs nbconvert — named follow-on), resource caps beyond the timeout, and
container isolation. C4's first slice (2026-09-25) consumes the trace and capture; verdicts
ran on a real paper for the first time on 2026-09-26 (AgroDesign, see C4); the Phase 0 gate
now has its signed bundle (C6, 2026-09-27); it waits on the owner's review of the `DIVERGED`.

## C4. Claim↔artifact binding & re-derivation verdict — **the moat**

**What:** bind each C1 claim to a value re-derived in C3 via a **locator** (JSON pointer, table
cell reference, regex/stdout capture, notebook cell), compare within a stated tolerance, and emit
the per-claim verdict: `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED`.

**Why:** this is the product. Everything else exists to make this verdict trustworthy.

**Design:** a model may *propose* a binding; the comparison and verdict are done by code. Any
failure to bind, run, or set a tolerance resolves to `UNVERIFIED` with a named cause. `DIVERGED`
requires the artifact's own run to contradict its own claim.

**Depends on:** C1 + C3. **Guardrail:** constraints #1, #3 — never `REPRODUCED` on a model's
say-so, never `DIVERGED` on a harness-side failure.

**Status (2026-09-25, first slice):** built under `src/plumb/verify/` — PRD and decisions
D1–D8 in `docs/planning/binding-verdict/prd.md`. `verify_claims(claims, bindings, run)` returns
exactly one evidence-carrying `Verdict` per claim (sorted, never dropped) plus a coverage
summary derived from the records, serialized canonically (byte-identical across processes).

- **Bindings** are a **user-written** JSON file (`load_bindings`); no proposer exists and
  `artifact_hint` is not read. Tolerances and scales must be decimal *strings*; a file that
  can't be trusted raises `BindingInvalid`.
- **Locators:** RFC 6901 JSON pointer, stdout regex (one group, exactly one match), CSV cell
  (column + one row key). Bytes are read only through `Capture.read` (hash re-checked); a stale
  target is `STALE_ARTIFACT` and never read; zero / many matches are `NO_BINDING` /
  `AMBIGUOUS_BINDING`; no float anywhere.
- **Compare** in a pinned `Decimal` context: a `Point` holds within the paper's **written
  precision** (closed half-unit band) or an explicit tolerance; a `Bound` by its operator. A run
  that wrote fewer digits than the paper is `ARTIFACT_PRECISION_COARSER` — checked first, so it
  is never a false `REPRODUCED`; round integers are `PRECISION_AMBIGUOUS`; percent claims need a
  declared scale (`UNIT_UNDECLARED`); `±`/CI/range/`~` are `UNSUPPORTED_VALUE_KIND`.
- **Run causes govern first** (no run → the run's failure → `NO_ARTIFACT`), so **no harness
  failure becomes `DIVERGED`** — pinned by `tests/verify/test_false_diverged_guard.py`, which is
  mutation-checked in-suite; every `DIVERGED` carries `review_required`. A catalogue test
  proves every cause in the closed vocabulary is emitted.

**First real paper (2026-09-26):** AgroDesign, arXiv:2603.09041 (`fixtures/gate/agrodesign/`;
survey and PRD in `docs/planning/gate-paper/`). 86 rule-defined claims (curated, grounded
verbatim — C1 recovered 0), **86 bound, 85 `REPRODUCED`, 1 `DIVERGED`**, 0 changed in an
environment resolved as of the code's date; the verdicts replay offline from the committed
trace and objects. Two engine gaps it exposed, fixed test-first: bindings may declare
`"float_repr": true` (pandas and `json` write the exact 2.5 as `2.5`, which is not a rounding —
without it the paper's `2.500` was a false `ARTIFACT_PRECISION_COARSER`), and `parse_trace`
reads a `RunTrace` back.

**Not built:** a binding proposer (`PROPOSER_UNGROUNDED`/`MODEL_ONLY_SIGNAL` stay reserved),
comparison of `PlusMinus`/`Interval`/`Range`/`Approximate`, notebook-cell locators, the
`plumb verify` CLI. **The Phase 0 gate's number and bundle exist; the gate waits on the owner's review of the one `DIVERGED`.**

## C5. Discrepancy corpus & calibration benchmark

**What:** accumulate every (claim, re-derived value, verdict, locator, cause) into a labeled
corpus; publish a precision/recall benchmark over a public paper corpus.

**Why:** the compounding moat and the credibility instrument. Precision on `DIVERGED` is the
number the whole reputation rests on.

**Depends on:** C4. **Guardrail:** constraint #4 — the corpus is the asset that a better base
model cannot hand you for free.

## C6. Signed, replayable reproduction bundle

**What:** a signed record binding paper hash + repo tree hash + environment + run traces +
per-claim verdicts, such that a third party can **replay** and reach the same verdicts.

**Why:** a finding nobody can independently replay is an opinion. This makes `DIVERGED`
defensible and `REPRODUCED` auditable.

**Depends on:** C4. **Guardrail:** constraints #2, #3 — only what the user chooses to publish is
in the bundle; the bundle is the evidence, not an accusation.

**Status (2026-09-27, first slice):** built under `src/plumb/bundle/` (PRD:
`docs/planning/signed-bundle/prd.md`). A bundle is a directory: `manifest.json` (format
`plumb-bundle/1`, paper identity, source + tree hash, run id, signer, every member's path /
SHA-256 / size) and its detached SSHSIG `manifest.sig` (`ssh-keygen -Y`, namespace
`plumb-bundle-v1`, Ed25519 — deterministic, no crypto dependency), plus the claims, bindings,
trace, verdicts, frozen environment, **only the outputs a binding reads** (never stderr), and
optionally the paper. `build_bundle` re-derives the verdicts itself and refuses to sign anything
`verify_bundle` would reject. `verify_bundle` checks the signature before reading anything
unsigned, then members, structure, refused content (local paths, stderr, outputs the run did not
produce), the claims — **re-admitted against the paper through the admission gate**
(`plumb.extract.admit.readmit`; `parse_claims` returns records, so reading bytes is never a
second door to `Claim`) — and the re-derived verdicts, reporting 11 named causes and never
raising on content. Because claims are re-grounded, verification needs the paper: bundled, or
supplied by the verifier and checked against its SHA-256. **The AgroDesign bundle**
(`bundles/agrodesign/`, signed with the dedicated `plumb-bundle` key; public key in
`bundles/allowed_signers`) verifies, including from a fresh clone, and
`tools/bundle_replay.py` re-ran it from a clean clone in the frozen environment with a
byte-identical run id. **Not built:** transparency logs / sigstore, timestamps, key rotation,
tar packaging, a `plumb bundle` CLI.

## C7. Internal-consistency checks (no-code path)

**What:** for PDF-only papers with no runnable artifacts, run statcheck/GRIM-style
internal-consistency checks (do the reported statistics agree with each other and the reported N).

**Why:** extends coverage to the majority of papers that ship no code — but as a **weaker,
clearly labeled** signal.

**Depends on:** C1 — specifically on C1's `StudyParameter` records, which carry the reported N
these checks are run against. N is deliberately *not* a `Claim`: no execution re-derives a sample
size, so counting it as one would distort the bind-and-re-derive coverage number.
**Guardrail:** constraint #3 — an internal inconsistency is labeled as such, never rendered as a
ground-truth `DIVERGED` from re-execution.

## C8. Hosted layer (BYOK, opt-in) — the business

**What:** a managed service journals, labs, and authors run submissions through, with the OSS
engine underneath. BYOK, opt-in, runs on infrastructure the customer authorizes.

**Why:** the revenue layer, on the usual OSS-on-ramp → managed-layer playbook.

**Depends on:** C4 + C5 + C6. **Guardrail:** constraint #2 — no raw-data egress the customer
didn't authorize; verdicts and bundles, not datasets.

---

## Sequencing summary

| Order | Capability | Rationale | Depends on |
|---|---|---|---|
| 1 | C1 Claim extraction | Defines the unit of work | — |
| 2 | C2 Artifact intake & pinned env | Reproducibility precondition | — |
| 3 | C3 Execution & result capture | Produces the re-derived value | C2 |
| 4 | **C4 Binding & verdict** | **The moat** | C1, C3 |
| 5 | C5 Discrepancy corpus & benchmark | Compounds + proves precision | C4 |
| 6 | C6 Signed replayable bundle | Makes findings defensible | C4 |
| 7 | C7 No-code consistency checks | Extends coverage (weaker signal) | C1 |
| 8 | C8 Hosted layer | The business | C4, C5, C6 |

**One-line mantra:** run the paper, check its numbers against what it actually produced, prove
which ones hold.
