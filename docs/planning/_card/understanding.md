# Phase 2 — Understanding: C1 claim-extraction core

Synthesized from two parallel agent digs (contract map + adversarial scope critique)
over `CLAUDE.md`, `VISION.md`, `docs/ROADMAP.md`,
`docs/technical/CAPABILITY_ROADMAP.md`, `docs/technical/ARCHITECTURE.md`, and the
card at `docs/planning/_card/issue.md`.

## Where this sits

**C1** (`CAPABILITY_ROADMAP.md:17-30`), the head of the pipeline
(`ARCHITECTURE.md:16-44`). No dependencies. Feeds **C4**, the moat. This slice does
**not** touch verdicts — but it defines the record C4 assigns verdicts *to*, so its
schema is load-bearing for the guardrail "execution decides"
(`ARCHITECTURE.md:8-10`).

## Headline finding

**The brief is materially under-specified in three ways that would bake in a
breaking change to C4.** The brief was written by `plumb-next` as a handoff, not as
a spec; the dig found it cuts more than it should.

### 🔴 U-1 — Nothing in the brief constrains *selection*

"Headline quantitative claim" appears 4× in `ROADMAP.md` (`:17-18`, `:21`, `:24`,
`:56`) and is operationalized nowhere. The brief's acceptance tests (b), (d), (e)
are all passed by an implementation that emits **every numeral in the document**.
Yet `CAPABILITY_ROADMAP.md:23` says "the claim is the unit of work."

This is the single largest hole, and it is not cosmetic: the Phase 0 gate number is
*fraction of headline claims bound* (`ROADMAP.md:17-18`). Under-extraction inflates
that fraction; over-extraction buries real claims in `UNVERIFIED` (R1,
`ROADMAP.md:56`). **The denominator is a product decision, not an implementation
detail.**

### 🔴 U-2 — The record is too narrow to bind, and the brief froze it in a test

- **`tolerance_hint` is required by `ARCHITECTURE.md:56`** and absent from the
  brief. The brief justifies this by citing the open tolerance question — but
  `ARCHITECTURE.md:154` defers the *policy* ("per-claim explicit vs a typed default
  per claim kind"), not the existence of a slot. `NO_TOLERANCE` is already a
  committed `UNVERIFIED` cause (`ARCHITECTURE.md:95-96`), so the field has a known
  consumer.
- **No `metric` / `subject` field.** `(value, units, span)` is not bindable: C4
  writes a locator (`ARCHITECTURE.md:83-85`) aimed at a *named quantity*. Without
  it, C4 must re-interpret the span text at bind time — inference where the design
  wants a contract.
- **`reported_value` as a float is a false-`DIVERGED` generator** (R2,
  `ROADMAP.md:57`): `p < 0.001` → `0.001`, `0.870` ≠ `0.87` on significant figures,
  `0.85 ± 0.03`, `95% CI [..]`, `12–15%` all lose information. `REPRODUCED` requires
  "matches exactly" (`ARCHITECTURE.md:90`), so precision must survive extraction
  verbatim.

### 🔴 U-3 — "DROPPED" contradicts the design's own vocabulary

The brief makes silent dropping an acceptance test (`issue.md:36-37`), and
`CAPABILITY_ROADMAP.md:29-30` agrees ("dropped, not carried forward as
`DIVERGED`"). But `ROADMAP.md:58` (R3 mitigation) says "**UNVERIFIED** when the
claim can't be grounded", `ARCHITECTURE.md:95` defines `PROPOSER_UNGROUNDED` as a
cause, and `ARCHITECTURE.md:97-98` insists "never a silent pass."

**The docs contradict each other.** Both readings are defensible; the PRD must pick
one and say so. Note the guardrail asymmetry: a silent drop is invisible to the
coverage number, which is the number the whole Phase 0 gate rests on.

## Other decisions the PRD must make

| # | Question | Why it matters |
|---|---|---|
| U-4 | **Citation location representation.** Char or byte offsets? Over raw or normalized text? | Only offsets round-trip (`issue.md:35-36`). If text is normalized (CRLF→LF, NFC, dehyphenation), offsets index the *normalized* text, which must then be what's content-addressed — else C6's paper hash (`ARCHITECTURE.md:113`) anchors different bytes. Make it a tagged union now or PDF (page+bbox) breaks the schema later. |
| U-5 | **Serialization + paper hash in scope?** | "Byte-identical output" has no referent without a defined serialized form, and C6 has nothing to bundle. The dig's verdict: the slice is **not** a coherent contract without these. |
| U-6 | **Is reported N a claim or metadata?** | C7 checks statistics against "the reported N" (`CAPABILITY_ROADMAP.md:93`) and depends on C1 (`:98`). If N is incidental here, C7 loses its input. |
| U-7 | **Markdown tables in or out?** | `CAPABILITY_ROADMAP.md:25` puts table parsing in the deterministic core. Also: "Markdown" appears in no design doc — all three say text/PDF/DOI. |
| U-8 | **Deduplication.** Same result in abstract + results + table: 1 claim or 3? | Directly distorts the gate denominator. |
| U-9 | **Artifact hint — paper-internal or repo-pointing?** | `ARCHITECTURE.md:57` says "artifact/table/figure". C2 doesn't exist yet, so repo-pointing invites speculative guessing. |

## Guardrail notes (`CLAUDE.md`)

- **#1 execution decides** — no `confidence: float` on `Claim`. It becomes
  `if confidence > 0.9` at verdict time, which is a model's opinion standing in for
  a re-derived value. Excluded by construction.
- **#4 gets better as models improve** — the **admission gate** (deterministic
  re-grounding, `ARCHITECTURE.md:59-61`) should be the *sole constructor* of a
  `Claim` even though the proposer is out of this slice. Otherwise the future
  proposer gets a second path that bypasses grounding. The gate is the part that
  improves with better models; the regexes are not.
- **#3 do not over-claim** — a related-work number attributed to *this* paper
  becomes a `DIVERGED` against the wrong authors (R4, `ROADMAP.md:59`).
- **#2 no egress** — fixtures synthetic or public-domain; C1 runtime deps
  stdlib/pure-parsing only (no `nltk`/`spacy`-class import-time model downloads);
  no absolute input paths in output.
- **Verdicts:** this slice emits none. Confirmed: C1 never assigns
  `REPRODUCED`/`DIVERGED`; it produces the claims C4 later binds by execution.

## Determinism (implementation-level, for the plan not the PRD)

`.gitattributes eol=lf` (offsets shift on CRLF); no `set` iteration or `hash()`
(`PYTHONHASHSEED` varies per process) — sort by explicit total key; `hashlib` only,
algorithm named, and pin *what* is hashed; `json.dumps` with `sort_keys` /
`ensure_ascii` / `separators` / indent / trailing newline all pinned; no
`generated_at`, no absolute paths (`Path.resolve()` differs under symlinks,
`/tmp`→`/private/tmp`); normalize Unicode once (NFC/NFD changes offsets); `re` is
leftmost-first so alternation order silently changes winners — document an
overlap-resolution rule; avoid `locale`; single-threaded as contract.

## Scope confirmed correctly cut

PDF→text, DOI resolution, the BYOK LLM proposer, tolerance *policy*, locator
grammar.

## ⚠️ Phase 0 accounting

This slice does **not** satisfy the Phase 0 C1 minimum. `ROADMAP.md:21` sets that at
"text/**PDF**". A second C1 slice (PDF→text) is required before the Phase 0 gate can
be cleared. The PRD must state this so C1 is not ticked off prematurely.
