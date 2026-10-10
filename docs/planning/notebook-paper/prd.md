# PRD — the first notebook-computed paper through the spine (`notebook-paper`)

Source: `_card/issue.md` (inline brief, successor to `notebook-cell-locator`), understanding
in `understanding.md` (panel screen + local probe). Candidate screening: `understanding.md`
"Selection" section. Owner: aliz.

## Problem statement

The notebook_cell locator is built and proven offline (PR #15, suite 1963). R1 — binding
coverage across papers, High/High — still has no case whose numbers are injected through a
notebook cell, the dominant failure class of both prior selection passes
(`docs/planning/gate-paper/survey.md:47-48`; `screening.md:293-294`). Until a real paper's
notebook-computed claims are bound, verdicted, and banked, the corpus cannot compound on the
class, and "notebook cell" as R1's named mitigation (`docs/ROADMAP.md:90`) is unproven.

## Goals & success metrics

- **G1 — A real notebook-paper case in the corpus.** A committed record under
  `fixtures/gate/rcai/` for arXiv:2609.00137 (Burtsev, "Recursive Criticality of AI
  Self-Improvement"): claims attempted, claims bound through `notebook_cell` locators,
  per-verdict and per-cause counts, produced by the built C2 → C3 (notebook entry) → C4
  spine on the paper's own repo at a pinned rev.
- **G2 — At least one claim's verdict flows through a `notebook_cell` locator**, read only
  by hash from a fresh cell artifact; the freshness guard is load-bearing: a committed
  notebook is `STALE_ARTIFACT`, never read (constraint #5).
- **G3 — Offline replay.** A test re-derives every verdict from the committed captured
  outputs and asserts the committed `verdicts.json` byte for byte; `--from-record --json`
  matches; no network.
- **G4 — Honest framing.** Claims count and C1 conformance are reported separately (the
  curated rule's recovery on this paper is conformance, not coverage); every `DIVERGED` is
  `review_required` and owner-labeled; denominators and label-authority markers in
  `corpus report`.
- **G5 — Determinism pinned.** Two dev-time runs (or run + replay) produce the same verdicts
  and the same located values; run-to-run reproducibility is the claim, env-version drift is
  recorded, not assumed away.

## Decisions (recommended; for approval at the review gate)

- **P1 — The paper.** arXiv:2609.00137v1 (2026-08), CC BY 4.0 (arXiv license marker; PDF
  committed as fixture with attribution). Code `github.com/burtsev/recursive-criticality-ai`,
  MIT, pinned at a recorded commit `HEAD^{tree}` (clone at probe time); repo = LICENSE +
  README + the single root notebook. No lockfile — README's stated versions are the declared
  dependency policy (C2), frozen resolve recorded in the record.
- **P2 — Claims are rule-encoded and span-grounded, fixed before binding.** Every numeric
  cell of the paper's §3 table (supercriticality regimes — `Weak supercriticality 3`,
  `12.90`, `24.73`, `11.83`, all rows) and §4.2 table (strategic-market regimes — all rows:
  `10.40 16.53 6.13 / 9.75 12.58 2.82 / 8.97 13.42 4.45`), plus the numeric statistics
  stated in §4 text (threshold R values and growth ratios the prose reports) — all of them,
  including any that turn out not to bind. Each `reported_value.text` must occur **verbatim**
  at its span in the normalized paper text (test-enforced); metric names descriptive
  (gate-paper P2 precedent). **The enumeration is itself fixed by the written rule and
  committed BEFORE the dev-time run** — the spec generator (rule-encoded tables → claims)
  is reviewed and committed first, so no claim can be added after seeing which bind; the
  fixture README records the rule verbatim (anti-inflation, gate-paper P2).
- **P2a — Paper member format (decided):** the arXiv **PDF** is the paper member (CC BY,
  canonical; pinned by SHA-256 in provenance). If `pdf_to_markdown` cannot place the §3/§4.2
  table spans (converter untested on this paper — its fixtures are biomedical), fall back to
  the arXiv **HTML** rendered to Markdown under the same verbatim-span rule; the format
  actually used is recorded in the fixture README. Either way the claims rule is against the
  *normalized text actually produced*, and the recovery-floor test surfaces the choice.
- **P3 — Bindings target the notebook's cell outputs.** `notebook_cell` locators pointing
  into the canonical outputs arrays of the cells that compute the tables (probe
  enumeration: cells 18 and 28 — re-pinned against the executed record at fixture time).
  `float_repr: true` declared per binding where the cell wrote shortest-repr doubles.
- **N1 — HTML table-cell addressing (engine amendment, owner-approved in-unit).** The
  probe finding: pandas `Styler._repr_html_` renders the paper's values only inside a
  single `text/html` string leaf (one `<td>` per value), and `text/plain` is a
  nondeterministic `Style at 0x…` repr — under the D1/D2 grammar zero cells are
  addressable, and this is the field's dominant notebook-rendering path (all three
  screened candidates render this way). Amendment:
  `{"kind": "notebook_cell", "pointer": "/0/data/text/html", "table": {"row": 2, "column": 2}}`
  — when `table` is present the pointed leaf MUST be HTML; the leaf is split
  deterministically on `<tr>` rows and `<td>` cells (tags stripped, text trimmed),
  `(row, column)` 0-based pins exactly one cell; out-of-range or no `<td>` →
  `NO_BINDING`; non-decimal cell text → `UNPARSEABLE_VALUE`; `float_repr` honored on the
  shared parse path; no new causes (D5 of the locator PRD holds); the `(row, column)` is
  user-written in the bindings file and auditable. `row`/`column` are exactly two
  non-negative JSON integers; schema violations raise `BindingInvalid` at load.
- **P4 — Environment built once, at dev time.** `tools/rcai_run.py` does the authorized
  fetch: resolve git at the pinned rev, describe environment, real `build_environment`
  (declared policy from README), real notebook execution via the C3 runner
  (`jupyter nbconvert --execute`), freeze the resolved versions into the record.
  Determinism is re-checked with a second dev-time run (M4a-style drift cross-check if
  feasible; the code has no era boundary — fresh resolve is the only env, recorded).
- **P5 — The record is committed and banked.** `fixtures/gate/rcai/` holds the paper PDF +
  provenance README (URLs, licenses, SHA-256), `claims.json` (C1 form), `bindings.json`,
  `trace.json`, `objects/` (locatable only), `verdicts.json`, environment + source records.
  `plumb verify --bank` folds it into `corpus/local/`; `corpus report` pools it; every
  `DIVERGED` gets an owner label. Runtime budget: full-notebook execution ≤ 20 minutes
  (screened ~5), measured and recorded.

## Must / should

**Must:** P1–P5; acceptance items 1–5 of `_card/issue.md`; suite green and network-free
(test-first); no new causes in any vocabulary; the whole-notebook wall time measured and
recorded in the provenance README.

**Should:** an M4a-style drift cross-check note even when only one env exists (state the
boundary, Perrin precedent); report per-paper C1 recovery as conformance with the grounded
rule's counts.

## Technical considerations

- Entry point: fallback notebook rule (C3) — no `[project.scripts]`, no root `main.py`, one
  root `*.ipynb`; `jupyter` must be in the checkout env (env builder installs it as declared
  tooling; `WONT_RUN` if absent — never a guess).
- The paper member: the arXiv PDF (CC BY) via `pdf_to_markdown`, with the HTML fallback
  (P2a); spans recorded against the normalized text actually produced (enforced verbatim,
  P2).
- numba (LLVM JIT) is the one compiled dependency — macOS arm64 wheels exist and JIT runs
  (probe evidence); recorded as a dependency of the environment, never a stub.
- Replay: record → `--from-record` byte-identical; bundle optional (not required for corpus
  banking; `--out` works if desired).

## Risks & open questions

- **R1 honest default:** any unbound/unrun claim is `UNVERIFIED` with cause and denominator
  — the number is reported with all claims, not only the ones that bind.
- **R2:** wrong cell pointer → wrong `DIVERGED` risk; every `DIVERGED` carries
  `review_required` + locator + artifact sha (auditable, not guessable); the false-`DIVERGED`
  guard already covers the stale path (PR #15).
- **Env drift:** the paper's own era is weeks old; the frozen fresh resolve is the recorded
  environment; run-to-run determinism (zero RNG) is the reproducibility claim.
- **Converter risk (R3-adjacent, was Gap A):** `pdf_to_markdown` is fixture-tuned for
  biomedical two-column PDFs; this arXiv PDF is new terrain. A deterministic converter fix
  is in scope ONLY test-first and fixture-guarded (the 5 seated fixtures' recovery floors
  must not move); otherwise the documented outcome is the HTML fallback (P2a) or a recorded
  partial-recovery conformance number — never a fabricated span.
- **Open:** the paper's §4.2 values are 2-decimal roundings of full-precision doubles — the
  `float_repr`-or-written-precision decision per claim is fixed by the existing compare rules
  (written precision band / `float_repr` declaration); no new comparison logic. The fixture
  pre-registers each claim's declared reading (written-precision band vs `float_repr` zero
  half-unit) in the bindings file, committed before the run — so the band question is
  answered before any verdict exists.
- **Open:** whether the fixture should also emit a signed bundle — not required for the
  corpus number; deferring (out of scope) unless the owner wants it at the gate.

## Out of scope

- New locators, new causes, comparison changes, or any engine work (the engine shipped in
  PR #15; this unit is fixture + campaign).
- Candidate 2 and 3 fixtures (Erwin, Patel) — recorded as screened; a second notebook paper
  is a later corpus-growth unit (the panel screen is the documented backlog).
- The C2 poetry env policy and C4 figure locators (other named engine gaps, unchanged).
- Publishing findings (R4) — nothing is published; owner-labeled corpus only.

## Guardrail check (CLAUDE.md)

Execution decides: verdicts come from `verify_claims` over the real dev-time run; labels are
human and owner-reviewed; no egress beyond the authorized dev-time fetch (recorded, never in
tests/CI); `UNVERIFIED` is the honest default with denominators; a committed notebook is
never read as a fresh result; test-first — the acceptance tests come before the fixture's
dev-time run.