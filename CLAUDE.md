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

Status: **the deterministic spine of C1 is built; nothing downstream is.** `src/plumb/extract/`
holds the record layer (`ClaimValue`, `Location`, `Claim`, `StudyParameter`), a paper hash,
byte-identical serialization, value-identity dedup, Markdown table parsing, exhaustive candidate
extraction, and the admission gate that is the sole constructor of a `Claim`. Zero runtime
dependencies; no network reachable from any test.

**Not built:** claim *selection* (which numbers in a paper **are** claims — the substance of C1),
PDF input, and the whole of C2–C8. **No verdict has ever been emitted**, because nothing that
emits one exists yet. The Phase 0 gate is not met.

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
