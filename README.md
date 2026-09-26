# Plumb

**Execution-grounded research-integrity verifier.** Point Plumb at a paper and the code and
data behind it; it re-runs the artifacts on your own compute, re-derives the paper's
quantitative claims from the actual run, and returns a per-claim, reproducible verdict —
surfacing the claims that do not hold.

> A plumb line is the oldest tool for testing whether something stands true. Plumb asks of a
> paper: *does the claim hold when you actually run it?*

Status: **early.** The deterministic extraction spine, the C2 artifact-intake spine, the C3
run spine and the first C4 binding & verdict slice exist and are tested (offline). The first
real paper has been run through the spine end to end (below). The Phase 0 gate's number now
exists; its signed, replayable bundle (C6) does not, so the gate is not met.

```
uv sync && uv run pytest        # 1427 tests, no network, one pinned runtime dependency (pypdf)
```

| | |
|---|---|
| **Built** | Typed claim records · paper hashing · byte-identical serialization · dedup · Markdown table parsing · candidate extraction · the admission gate · claim selection (M3 rule) · PDF→Markdown conversion (single- and two-column layouts; all five fixtures at the recovery floor — see `fixtures/papers/README.md`) · **artifact intake** (tree hash via plumb bytes framing or the repo's `HEAD^{tree}`; local/git/archive resolution; environment descriptor; offline-tested, real `uv sync` dev-time only) · **execution & capture** (entry-point resolution; runs in a working copy under the run area; content-addressed stdout/JSON/CSV; freshness guard — stale outputs are never read) · **binding & verdict, first slice** (user-written bindings; JSON-pointer / stdout-regex / CSV-cell locators; `Point`/`Bound` compared against the paper's written precision or an explicit tolerance; a closed `UNVERIFIED` cause vocabulary; no harness failure can become `DIVERGED`, mutation-checked) |
| **Not built** | the signed bundle (C6) · automatic claim extraction on the gate paper (C1: 0/86) · binding proposer · other value kinds (±, CI, range, ~) · notebook capture · `plumb verify` CLI · corpus · bundle · hosted layer |

**The first real paper.** *AgroDesign* (arXiv:2603.09041, CC BY 4.0) was run through intake →
run → verify on its own code at a pinned tag: of 86 rule-defined claims (every numeric cell of
its eight results tables and every test statistic in its §4 prose), **86 bound, 85
`REPRODUCED`, 1 `DIVERGED`** — a Shapiro-Wilk p reported as 0.034 that its own code computes as
0.03455. The divergence is unchanged in an environment resolved as of the code's date, is
flagged for review, and has not been published. Plumb's automatic claim extraction recovered
**0** of those 86 claims; they were curated by a fixed rule and grounded verbatim. Details:
`fixtures/gate/agrodesign/README.md`.

## What it is (and is not)

- **Is:** re-derive a paper's own numbers by re-executing its own artifacts, and diff them.
- **Is not:** an LLM that reads a paper and guesses whether it is wrong (measurably unreliable),
  a plagiarism/AI-text detector, or a misconduct accusation engine.

The verdict is honest and per-claim: `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` /
`UNVERIFIED` — and `UNVERIFIED` is never dressed up as `REPRODUCED`. A model may extract a claim
or propose a binding; only **execution** decides the verdict.

## Docs

- [`VISION.md`](VISION.md) — the thesis, the moat, non-goals.
- [`CLAUDE.md`](CLAUDE.md) — guardrails and the verdict contract.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — phased plan and risk register.
- [`docs/technical/CAPABILITY_ROADMAP.md`](docs/technical/CAPABILITY_ROADMAP.md) — C1..C8 in build order.
- [`docs/technical/ARCHITECTURE.md`](docs/technical/ARCHITECTURE.md) — the design.

## Lineage

Plumb generalizes a "reproduce & verify published work" capability out of genomics and points it
at the literature at large.
