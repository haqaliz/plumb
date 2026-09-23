# PRD — PDF input for C1 (slug: `pdf-input`)

## Problem Statement

The Phase 0 gate's C1 minimum is "extract a paper's headline quantitative claims from
**text/PDF**" (`docs/ROADMAP.md:21`). The deterministic spine of C1 has landed for text and
Markdown — record layer, candidates, admission gate, and the M3 selection rule — but **PDF
input is not built** (`docs/technical/CAPABILITY_ROADMAP.md:41,47-49`: "the gate is not met and
C1 must not be read as complete"). Papers ship as PDFs; a verifier that cannot read them cannot
reach the gate's first number. This slice completes C1's input surface so the gate's C1
prerequisite is met (C2–C4 remain for the gate itself).

## Goals & Success Metrics

Convert a paper PDF to Markdown-equivalent plain text — deterministically, offline, with no
network reachable from any test — and feed it through the existing `extract_claims(raw)` seam
(`src/plumb/extract/pipeline.py:29-61`) **unchanged**, so that a PDF and the equivalent
Markdown yield the same claims by identity.

Success = the five acceptance criteria below pass, the existing determinism and no-network
suites stay green, and the Phase 0 gate's C1 prerequisite ("text/PDF") is met on the record.

### Acceptance criteria (test-first — these are the failing tests written before the code)

1. A PDF fixture of a CC BY paper parses to text **byte-identically across processes** (the
   cross-process determinism bar of `tests/extract/test_determinism.py`).
2. Claims extracted from the PDF **equal claims extracted from the paper's Markdown by
   `Claim.id`** (value text + metric + units — `src/plumb/extract/claim.py:61-70`; location is
   excluded by design). The comparison is by id, never full-record equality: the two inputs
   are different documents and `Location` fields legitimately differ. **Recovery floor
   (approved at the review gate):** every claim the Markdown path finds in the **abstract
   section** must be recovered by the PDF path by id, and the per-paper claim-id recovery
   rate across the whole paper must be **≥ 90%** for the fixture to count as passing; table
   cells are excluded from the bar in this slice and counted separately (reported, never
   gamed). The per-paper recovery rate is reported in the test output (S1).
3. `Location` records remain `CharSpan` over the converted text, satisfying the span
   round-trip (`text[location.start:location.end] == claim.reported_value.text`). **The
   `PageBox` variant (PDF page/bbox) is explicitly deferred to a follow-on slice** — the union,
   serializer, ordering key, closed schema, and hash-anchoring contracts are not touched here.
4. No network is reachable from any test (autouse blocker in `tests/conftest.py:56-60`;
   `tests/extract/test_no_network.py` stays green), and the PDF dependency performs no network
   I/O at import or parse time.
5. The slice ships test-first: each aspect's first commit is its failing test.

## User Personas & Scenarios

- **A researcher** with a paper PDF and (optionally) its repo, running the future `plumb
  verify <paper> <repo>` — the paper side of that invocation will be a PDF more often than
  not.
- **The Phase 0 gate**: the honest number ("what fraction of headline claims can we bind and
  re-derive") is computed over a corpus of runnable papers; the paper side of that corpus is
  PDFs once this slice lands.
- **Internal**: the five CC BY fixtures are Markdown today (`fixtures/papers/README.md`); this
  slice adds their real PDFs so every downstream capability exercises the real input format.

## Requirements

### Must-have

- **M1. Pinned PDF dependency.** `pypdf` (pure-Python, BSD, no runtime deps, no network),
  pinned exactly, added to `pyproject.toml` (`dependencies = []` today — `pyproject.toml:7`).
  The "zero runtime dependencies" claims in `CLAUDE.md:25`, `CAPABILITY_ROADMAP.md:39`, and
  `README.md:9` are amended to reflect the single pinned dependency. (Agreed in interview:
  pypdf + our own reconstruction heuristics, not pdfplumber/PyMuPDF.)
- **M2. Converter module.** `src/plumb/pdf/` — a new package, deliberately **outside**
  `src/plumb/extract/` so the deterministic-core AST import allowlist
  (`tests/extract/test_determinism.py:1048-1062`) is not amended; the converter still inherits
  the network blocker and all record contracts. Deterministic `pdf_to_markdown(pdf_bytes) ->
  str` that emits **Markdown-equivalent text**: ATX headings (detected via pypdf's font-size
  visitor) and GFM pipe tables (reconstructed by our own deterministic heuristics). This is
  required, not cosmetic: section hints come from `##` headings (`candidates.py:341-359`) and
  cells from pipe tables (`tables.py:26-36`); without them every candidate lands in `other`
  and selection rejects all (`selection.py:446-447`).
- **M3. Real PDF fixtures.** The five CC BY papers' real journal PDFs fetched from Europe PMC
  (authorized-fetch precedent: `fixtures/papers/README.md:15-17`), committed as binary
  fixtures with a `.gitattributes` binary rule (current `* text=auto eol=lf` would mangle
  them), and documented in `fixtures/papers/README.md` (including resolving the two known
  DOI/README provenance discrepancies: PMC12780771, PMC13363872). The fetch is a one-time
  dev-time step (tool script), never run in tests. **Signal survey (approved at the review
  gate):** the fixtures aspect's acceptance includes a measured survey on the first fetched
  PDF — heading-detection recovery and table-reconstruction recovery against its Markdown —
  whose numbers set the reconstruction design and the per-fixture floor before the frontend
  aspect locks its design.
- **M4. Fixture-failure policy (approved at the review gate).** A fixture whose extraction
  cannot clear the ≥ 90% claim-id recovery floor after honest reconstruction effort is
  **excluded from the equality bar and documented as such** in `fixtures/papers/README.md`
  (with the measured recovery rate) — the slice does not hard-fail on it, and the exclusion
  is never silent. The floor itself is set by the survey (M3).
- **M4. Seam integration tests.** `extract_claims(pdf_to_markdown(pdf))` runs over every PDF
  fixture; claim-id equality vs the Markdown-derived claims per paper; span round-trip holds;
  cross-process byte-identity test; the full suite (including `test_determinism.py` and
  `test_no_network.py`) stays green.
- **M5. Doc amendments.** `CAPABILITY_ROADMAP.md` C1 status ("PDF input" no longer in the
  "Not built" list; gate C1 prerequisite met), `CLAUDE.md`, `README.md` status lines, and the
  dependency claim amendments from M1.

### Should-have

- **S1. Coverage accounting.** The equality tests report an honest per-paper recovery figure
  (claims found via PDF vs claims found via Markdown, by id), so a known table-reconstruction
  gap is a measured number, not a silent one — consistent with the repo's "never a silent
  pass" ethos.

### Nice-to-have

- **N1.** A one-line CLI seam (`plumb pdf <file.pdf>`) — only if it falls out of M2 without
  extra surface; otherwise defer to the Phase 1 CLI.

## Technical Considerations

- **Capability:** C1 (`CAPABILITY_ROADMAP.md:17-49`). Depends on nothing; it completes C1.
- **The seam is the contract:** `raw: str`, normalized once (`location.py:26-47`), spans index
  the normalized bytes, `hash_paper` rejects bytes (`hashing.py:116-120`). The converter's
  output is fed to `extract_claims` as-is; no pipeline change.
- **Determinism:** pypdf text extraction is deterministic for fixed bytes; all reconstruction
  is our code. Cross-process byte-identity is pinned by a test (subprocess, varying
  `PYTHONHASHSEED` — the `test_determinism.py` pattern).
- **No-network:** autouse `_block_network` covers every test (`conftest.py:56-60`). The
  dependency and our module must perform zero network I/O at import or use.
- **Verdict impact:** none. This slice produces text for C1; it never assigns a verdict.
  Execution-grounded rule untouched (`CLAUDE.md` #1).
- **Fixture plumbing:** `.gitattributes` needs a `-text` rule for `*.pdf`; the line-ending
  pinning test (`test_determinism.py:1135-1160`) must stay green.
- **Prior art considered and rejected:** GROBID (scholarly-standard PDF→TEI, but a Java
  service — not pure-Python, violates the brief's wording); pdfplumber (table extraction but
  adds pdfminer.six + Pillow runtime deps); PyMuPDF (AGPL). All documented here so the choice
  isn't relitigated.

## Risks & Open Questions

- **R3 (claim-extraction error, Med/High)** — the operative risk. Table/heading reconstruction
  from a real journal PDF is heuristic; a mangled number becomes candidate noise (handled by
  the admission gate, but coverage drops). Mitigation: S1's measured recovery figure; the
  acceptance bar is claim-id equality on fixtures whose claims are recoverable, stated
  honestly rather than gamed.
- **Fixtures may not re-fetch cleanly.** Europe PMC PDF endpoints can change; the fetch is a
  one-time dev step with the source URLs recorded in `fixtures/papers/README.md`.
- **Heading detection quality** depends on the journal's font encoding; some journals embed
  text without reliable font-size signals. The converter's heuristic must fail to a named
  fallback (e.g., TOC/heading line heuristics) rather than silently emitting flat text that
  selection would reject wholesale.
- **Open question:** should heading reconstruction also handle the `# Title` (H1) line the
  fixtures carry (`PMC13134363.md:3`)? Decide in the aspect spec; the fixtures set the bar.

## Out of Scope

- **`PageBox` Location variant** (page/bbox in the record) — deferred follow-on slice;
  criterion 3 of the original brief is re-scoped to CharSpan-over-converted-text and the
  span round-trip.
- **DOI resolution** (`ARCHITECTURE.md:55`) — later C1 slice.
- **BYOK LLM proposer** (`ARCHITECTURE.md:70-73`) — deterministic spine ships first.
- **C7 statcheck/GRIM consistency path** (`CAPABILITY_ROADMAP.md:109-121`) — downstream of C1,
  separate unit.
- **Any verdict emission** — nothing here assigns `REPRODUCED` / `DIVERGED` / `UNVERIFIED`.

## Proposed Aspect Decomposition

1. `fixtures` — fetch the five real PDFs from Europe PMC, `.gitattributes` binary rule,
   fixture-loading convention, README provenance update (incl. DOI discrepancies), and the
   **signal survey** (heading/table recovery measured on the first PDF, setting the floor).
2. `frontend` — `src/plumb/pdf/` converter (pypdf pinned; heading + pipe-table
   reconstruction; a named line-joining rule for value-bearing text — `normalize_text` does
   not collapse whitespace, so a PDF line break inside a value would change its claim id;
   determinism; no-network) with its failing tests first.
3. `seam` — integration acceptance: claim-id equality vs Markdown per paper with the ≥ 90%
   floor, span round-trip, cross-process byte identity, recovery accounting (S1), fixture
   exclusions documented per M4, doc amendments (M5).

Sequencing: `fixtures` → `frontend` → `seam` (tests in each aspect depend on the PDFs).

## Follow-on slice — `columns` (opened at the seam checkpoint, 2026-09-22)

The `seam` checkpoint measured the honest number: PMC13134363 (single-column) clears both
floors; the four two-column fixtures (Oxford, MDPI ×2, Springer) recover 0–28% of non-table
claims and were excluded per M4. The failure is structural — pypdf interleaves two-column
content streams and the converter's line reconstruction is single-column-oriented — and
bounded: the visitor already exposes text-matrix coordinates. The `columns` aspect
(`columns/spec.md`, `columns/plan_20260922.md`) adds column-aware reconstruction so the
excluded fixtures clear the floors, then re-qualifies the docs to the true coverage. M4
remains the honest fallback for any residual.