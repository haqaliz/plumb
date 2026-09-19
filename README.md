# Plumb

**Execution-grounded research-integrity verifier.** Point Plumb at a paper and the code and
data behind it; it re-runs the artifacts on your own compute, re-derives the paper's
quantitative claims from the actual run, and returns a per-claim, reproducible verdict —
surfacing the claims that do not hold.

> A plumb line is the oldest tool for testing whether something stands true. Plumb asks of a
> paper: *does the claim hold when you actually run it?*

Status: **greenfield** — design docs only; the engine is not built yet.

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

Plumb generalizes Contig's "reproduce & verify published work" capability out of genomics and
points it at the literature at large. Sibling of Belay, Contig, and Whetstone.
