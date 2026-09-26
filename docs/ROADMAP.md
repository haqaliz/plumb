# Plumb Roadmap

Phased plan and risk register. Capability-level detail (C1..C8) lives in
[`technical/CAPABILITY_ROADMAP.md`](technical/CAPABILITY_ROADMAP.md); the design lives in
[`technical/ARCHITECTURE.md`](technical/ARCHITECTURE.md). This file is the "what order, and what
could kill it" view.

The one-line goal for the first 1–3 months (owner-set, 2026-09-20): **find real, verifiable
errors in real papers and publish them, with a reproducible bundle behind each finding.** The
first corpus is deliberately narrow — Python/R data-analysis papers whose code actually runs —
so the wedge (C4) can be proven before the ambition (domain-agnostic) is chased.

---

## Phase 0 — Prove the wedge (weeks 0–4)

Goal: over a small public corpus of runnable papers, produce the honest number — *what fraction
of headline claims can we bind and re-derive, and how many DIVERGE* — with a first credible
finding.

- C1 (minimum): extract a paper's headline quantitative claims from text/PDF.
- C2 (minimum): resolve a local path or git URL to a pinned checkout on the user's compute.
- C3 (minimum): run the repo's own entry point and capture structured output, freshness-guarded.
- C4 (minimum): bind one headline claim to a re-derived value and emit the verdict. *(First
  slice built 2026-09-25 — `src/plumb/verify/`. First real paper run 2026-09-26: AgroDesign,
  86 bound, 85 `REPRODUCED`, 1 `DIVERGED`; `fixtures/gate/agrodesign/`.)*
- **Gate:** at least one real, reproducible `DIVERGED` (or a clean panel of `REPRODUCED`) with a
  bundle a third party can replay. If C4 can't clear a conservative false-positive bar, stop and
  rethink before building further. **Status (2026-09-27):** the panel is real and reproducible (85 `REPRODUCED`, 1 `DIVERGED`),
  signed (`bundles/agrodesign/`), verified offline, and its run replayed byte-identical from a
  clean clone (`bundles/README.md`). **Outstanding: the owner's review of the `DIVERGED`** before
  the gate is declared met.

## Phase 1 — OSS core (months 1–2)

Ship the self-hostable CLI: C1–C4 hardened + C6 (signed replayable bundle). `plumb verify
<paper> <repo>` returns a per-claim verdict table and a bundle. BYOK LLM assist is opt-in and
off by default. Publish the method.

## Phase 2 — Corpus + benchmark + no-code path (months 2–3)

- C5: bank every (claim, re-derived value, verdict) into the discrepancy corpus; publish a
  precision/recall benchmark over a public corpus.
- C7: internal-consistency (statcheck/GRIM-style) path for PDF-only papers, clearly labeled as a
  weaker, internal-inconsistency signal — never a ground-truth `DIVERGED`.
- Publish the first batch of verifiable findings.

## Phase 3 — Hosted layer (post month 3, demand-pull)

- C8: managed, BYOK, opt-in service for journals/labs/authors. First design partner.
- Only after C4's precision is defensible and the corpus has teeth.

---

## Risk register

Ordered by kill-the-project potential. L = likelihood, I = impact.

| # | Risk | L | I | Mitigation |
|---|---|---|---|---|
| R1 | **Binding coverage** — most repos don't run, or never expose the headline number in a machine-readable place (~3.2% of notebooks reproduce). Verdicts pile up as `UNVERIFIED`. | High | High | Multiple locator types (JSON pointer, table cell, regex/stdout, notebook cell); freshness guard; `UNVERIFIED` (not `DIVERGED`) as the honest default; narrow first corpus to runnable papers. |
| R2 | **False `DIVERGED`** — a discrepancy that is our harness's fault (env drift, wrong binding) published as a paper error. Reputational poison. | High | High | `DIVERGED` only when the artifact's *own* run contradicts its *own* claim; conservative tolerance; human-in-the-loop before any finding is published; the signed bundle must replay for a third party. |
| R3 | **Claim-extraction error** — the LLM proposes a claim the paper didn't make, or misreads a number. | Med | High | Deterministic verification of the extracted claim against the paper text; execution never trusts the proposer; an ungroundable candidate surfaces as a non-claim with a named cause (M4), never a silent drop and never `UNVERIFIED` — C1 emits no verdicts. |
| R4 | **Legal / ethical** — publishing "errors" against named papers and authors. | Med | High | Publish only verifiable, reproducible, conservative findings + the bundle + the method; frame as reproduction discrepancy, never misconduct; give authors a right of reply. |
| R5 | **Egress** — sending papers/data to a cloud LLM by default. | Med | Med | BYOK, local-model option, runs on the user's compute; only hashes/verdicts the user chooses leave; off by default. |
| R6 | **Domain-agnostic ambition vs 3-month reality.** | Med | Med | First corpus = Python/R data-analysis papers that run; generalize only after C4 holds there. |
| R7 | **Slow enterprise / journal sales.** | Low | Med | OSS reputation + published findings first; hosted layer is demand-pull, not the opening move. |

Keep this register honest. If a mitigation stops being true, downgrade the phase, don't the risk.
