<div align="center">

<img src="https://raw.githubusercontent.com/haqaliz/plumb/master/assets/plumb-logo.png" alt="Plumb" width="110" />

# Plumb

**Execution-grounded research-integrity verifier: re-runs a paper's own artifacts on your compute and returns a per-claim, reproducible verdict.**

Point Plumb at a paper and the code behind it. It pins the code, builds an environment, **re-runs the artifacts**, re-derives the paper's quantitative claims from what the run actually produced, and renders an honest verdict per claim — `REPRODUCED` / `WITHIN-TOLERANCE` / `DIVERGED` / `UNVERIFIED` — decided by *re-execution*, never by a model's opinion of the paper.

[![Status](https://img.shields.io/badge/status-alpha%20·%20engine%20built-3fb950)](docs/ROADMAP.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-DE5FE9?logo=astral&logoColor=white)](https://github.com/astral-sh/uv)
[![One runtime dep](https://img.shields.io/badge/runtime%20deps-one%20(pypdf)-3fb950)](pyproject.toml)
[![Offline tests](https://img.shields.io/badge/tests-2021%20offline%20·%20no%20network-3fb950)](tests/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-3fb950)](https://github.com/haqaliz/plumb/issues)

[Quickstart](#quickstart) · [How it works](#how-it-works) · [The verdict](#the-verdict) · [The number so far](#the-number-so-far) · [Vision](VISION.md) · [Roadmap](docs/ROADMAP.md) · [Contributing](#contributing)

<br/>

<img src="https://raw.githubusercontent.com/haqaliz/plumb/master/assets/plumb-verify.png" alt="plumb verify --from-record fixtures/gate/rcai: a real replay of the Burtsev, arXiv:2609.00137 record — the notebook-computed paper. 31 claims, 30 bound through notebook_cell locators: 30 REPRODUCED, 1 UNVERIFIED (NO_BINDING), 0 DIVERGED; the replay is byte-identical to the committed verdicts." width="830" />

<sub><b>The card is a real replay, not a mock.</b> It shows the committed record of the first notebook-computed paper through the spine (<a href="fixtures/gate/rcai/README.md">fixtures/gate/rcai</a>). The numbers the paper printed in its own notebook cells were re-derived by re-executing that notebook and bound through <code>notebook_cell</code> locators. C1 conformance on this paper is 0/31 — reported as conformance, never as coverage.</sub>

</div>

---

## Why Plumb

Three kinds of tools sit near the literature. Text-mining tools *extract* numbers. LLM judges *opine* on them. **Plumb is the third thing: the verifier.** It answers the question none of the others do — *"does the claim hold when you actually run it?"* — by re-executing the paper's own artifacts and diffing the re-derived value against the reported one.

Why that question matters, and why a judge can't answer it:

- **Frontier models hit only ~6.1% precision / ~21.1% recall on real errata-worthy errors** (SPOT, [arXiv 2505.11855](https://arxiv.org/abs/2505.11855)) — well below the bar for flagging a paper.
- **Only ~3.2% of published computational notebooks reproduce** (widely cited) — a paper's numbers often cannot be rebuilt at all, which is itself the finding.
- **Free AI tools cannot reliably flag even retracted literature** (JMIR 2026) — a guess about correctness is not verification of it.

Plumb's verdict is **grounded in execution, not opinion** — which means it gets *better* as base models improve (they write cleaner claims and better bindings), never redundant.

- 🪢 **The name.** A *plumb line* is the oldest tool for testing whether something stands true — and "to plumb" is to investigate to the bottom. Plumb asks of a paper: *does the claim hold when you actually run it?*
- 🔁 **Re-derive, don't re-read.** The value is re-derived from the paper's own run on your compute — never from a committed output, never from a stale file (a result that predates the run is `UNVERIFIED`, never parsed).
- ⚖️ **An honest verdict contract.** `REPRODUCED` means the paper's number was re-derived within its written precision; `DIVERGED` means the artifact's own run contradicts the paper's claim — and `UNVERIFIED` is never dressed up as either. A discrepancy that could be our harness's fault resolves to `UNVERIFIED`, never `DIVERGED`.
- 🧾 **Signed, replayable bundles.** Every finding ships with a hash-listed, `ssh-keygen -Y`-signed record — paper hash, tree hash, frozen environment, traces, verdicts — that a third party can replay byte-identical. A finding nobody can replay is an opinion.
- 📈 **A compounding discrepancy corpus.** Every (claim, re-derived value, verdict) banks as a labeled, replay-validated case; `plumb corpus report` pools coverage / precision / recall with denominators and label-authority markers, measured against **human** labels.
- 🔒 **Runs on your compute.** The paper, the repo, and the data never leave your machine; only hashes and the verdicts you choose to publish ever do.
- 🧪 **Test-first, deterministic.** A 2,000+-test offline suite pins determinism byte-for-byte; no network is reachable from any test; one pinned runtime dependency (`pypdf`).

> **Honesty is the whole product.** `UNVERIFIED` is *never* rendered as `REPRODUCED`, extraction conformance is never reported as coverage, and a `DIVERGED` that owner-review refutes (a run-to-run artifact, not a paper error) stays refuted — the corpus says so. Read [The number so far](#the-number-so-far) before trusting any claim.

---

## Quickstart

```bash
uv sync && uv run pytest        # 2,021 tests, no network, one runtime dep (pypdf)
```

**Verify a paper live:**

```bash
uv run plumb verify <paper> <repo> [--rev REV] [--bindings bindings.json]
#   <paper>  a local PDF/Markdown — the claims are extracted and selected by rule
#   <repo>   a local dir, git URL (with --rev), or archive — pinned checkout + env
#   --bindings   your user-written bindings: which captured value each claim is checked against
```

**Replay a committed record, byte-identical:**

```bash
uv run plumb verify --from-record fixtures/gate/rcai --json
uv run plumb verify --from-record fixtures/gate/rcai --bank   # fold into the discrepancy corpus
```

Exit contract: `0` iff every claim is decided; `1` on any `UNVERIFIED` or named cause; `2` on usage. Never a traceback; a harness failure is never a `DIVERGED`.

---

## How it works

The spine: **intake → run → re-derive → verdict → bundle** (`plumb verify` runs it end to end).

```
paper (text/PDF)                      repo/data (path | git URL --rev | archive)
       │                                        │
       ▼                                        ▼
 C1  extract & select claims   ──┐      C2  pinned checkout + frozen environment
       │   (typed Claim records) │          │
       │                         │          ▼
       │                         │  C3  run the repo's own entry point
       │                         │      (script | [project.scripts] | root main.py
       │                         │       | notebook via nbconvert — freshness-guarded,
       │                         │        content-addressed outputs)
       │                         │          │
       └──────────────┬──────────┘          ▼
                      ▼                re-derived values
                 C4  bind each claim to a value via a locator
                     (JSON pointer · stdout regex · CSV cell ·
                      notebook cell output · notebook HTML table cell)
                     → compare within the paper's written precision or a declared tolerance
                     → REPRODUCED / WITHIN-TOLERANCE / DIVERGED / UNVERIFIED
                      │
                      ├────────────►  C5  discrepancy corpus (bank every case)
                      ▼
                 C6  signed, replayable bundle (paper hash + tree hash + env + traces + verdicts)
```

- **The claim is the unit of work.** C1 emits typed, self-describing `Claim` records — reported value (verbatim), units, metric, paper location — through a deterministic admission gate; a candidate the paper didn't make is recorded as a non-claim with a named cause, never a silent drop. An optional BYOK LLM *proposer* may suggest candidates; every proposal is re-grounded against the paper text before admission and never assigns a verdict.
- **Reproduce what ran, not what was committed.** C3 executes the repo's own entry point in a working copy under the run area and captures stdout / JSON / CSV / notebook cells into a per-run object store keyed by SHA-256. An output whose mtime predates the run start is `STALE_ARTIFACT` — its bytes are never read.
- **Notebooks are first-class.** A root `*.ipynb` is the fallback entry point (`jupyter nbconvert --execute`); each output-bearing cell becomes a content-addressed artifact, and a claim binds into it — including `<td>` cells inside pandas Styler HTML, the way notebooks actually render tables.
- **The verdict is decided by code, in pinned `Decimal`.** No float reaches a comparison; run causes govern every claim first; every `DIVERGED` carries `review_required`.

## The verdict

| Verdict | Meaning | May be emitted when |
|---|---|---|
| **REPRODUCED** | The paper's value was re-derived from its own run, within tolerance | The artifact ran, the value bound, and it matches |
| **WITHIN-TOLERANCE** | Matches within a stated numeric tolerance, not exactly | Same, with a non-zero delta inside the tolerance band |
| **DIVERGED** | The re-derived value contradicts the paper's claim | The artifact ran and its own output contradicts the paper — never on a harness-side failure |
| **UNVERIFIED** | We could not decide | Repo won't run, claim won't bind, result is stale, tolerance can't be set — the honest default |

A model may extract a claim or propose a binding; **execution** assigns the verdict.

---

## The number so far

<img src="https://raw.githubusercontent.com/haqaliz/plumb/master/assets/plumb-corpus.png" alt="plumb corpus report: 3 banked cases — Perrin (16 claims: 2 REPRODUCED, 14 DIVERGED, all refuted on review), AgroDesign (86 claims: 85 REPRODUCED, 1 DIVERGED, confirmed), Burtsev rcai (31 claims: 30 REPRODUCED, 1 UNVERIFIED). Totals: 133 claims, 132 bound, 117 REPRODUCED, 15 DIVERGED, 1 UNVERIFIED, precision 1/15, recall 1/15 (owner labels)." width="830" />

Three real papers are banked — each record replays byte-identical and every labeled verdict is owner-reviewed:

- **AgroDesign** (arXiv:2603.09041) — 86 rule-defined claims, **85 `REPRODUCED`, 1 `DIVERGED`**: a Shapiro-Wilk p reported as `0.034` that its own code computes as `0.03455`, confirmed genuine on review and unchanged in a paper-era environment. C1 recovered 86/86 of its claims (conformance to the curated rule; `fixtures/gate/agrodesign/README.md`).
- **Perrin** (arXiv:2401.11842) — 16 claims, 2 `REPRODUCED`, **14 `DIVERGED` … refuted on review**: the artifact is *not* run-to-run reproducible at the paper's written precision (unseeded worker RNG; noise ~0.005–0.010 vs written precision 0.001; four verdict flips across three runs). A reproducibility finding about the artifact, not a paper error — recorded as refuted, never published as a discrepancy.
- **Burtsev** (arXiv:2609.00137) — the first notebook-computed paper through the spine: 31 claims, **30 `REPRODUCED` through `notebook_cell` locators**, 1 `UNVERIFIED` (`NO_BINDING`), 0 `DIVERGED`; 70 s wall; a second full run changes zero verdicts (`fixtures/gate/rcai/README.md`).

**Totals: 133 claims, 132 bound, 117 `REPRODUCED`, 15 `DIVERGED` (14 refuted, 1 confirmed), 1 `UNVERIFIED` — precision/recall 1/15 against owner labels.** The 1/15 is the honest number: *one* republishable discrepancy out of fifteen flagged, because fourteen were the artifact's own run-to-run noise. The runnable-paper space is thin (consistent with ~3.2% notebook reproduction), and growing the panel is blocked by named engine gaps — a poetry env policy (C2), figure-with-data locators, and the fact that most papers ship no code at all (the C7 no-code path).

---

## Docs

- [`VISION.md`](VISION.md) — the thesis, the moat, non-goals.
- [`CLAUDE.md`](CLAUDE.md) — guardrails and the verdict contract.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — phased plan and risk register (R1–R7).
- [`docs/technical/CAPABILITY_ROADMAP.md`](docs/technical/CAPABILITY_ROADMAP.md) — C1..C8 capabilities in build order.
- [`docs/technical/ARCHITECTURE.md`](docs/technical/ARCHITECTURE.md) — the design.
- [`fixtures/gate/`](fixtures/gate/) — the banked real-paper records with provenance.

## Contributing

Test-first is the house rule: every capability lands with its failing test written first, the suite runs offline, no network is reachable from any test, and a verdict is never assigned by a model. See [`CLAUDE.md`](CLAUDE.md) before opening an issue.

## Lineage

Plumb generalizes a "reproduce & verify published work" capability out of genomics and points it at the literature at large — the deterministic spine (intake → run → re-derive → verdict → bundle) plus a compounding discrepancy corpus that gets sharper as base models improve.