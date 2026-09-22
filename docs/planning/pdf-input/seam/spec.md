# Aspect spec: `seam` — PDF through the C1 pipeline, acceptance

## Problem slice

Prove the slice's promise end-to-end: `extract_claims(pdf_to_markdown(pdf))` yields the same
claims as `extract_claims(markdown)` by `Claim.id`, with an honest recovery floor, the span
round-trip intact, and the whole suite green. This is where the PRD's acceptance criteria
1–2 and 4–5 are pinned as tests, and where the docs get amended so C1's "Not built: PDF
input" is no longer true.

## In-scope

- Seam integration tests over every PDF fixture:
  - `extract_claims(pdf_to_markdown(pdf_bytes))` runs without error on all five fixtures.
  - **Claim-id equality vs the Markdown path** per paper: every abstract-section claim found
    by the Markdown path is recovered by the PDF path by id; whole-paper recovery ≥ 90%
    (PRD criterion 2, floor approved at the gate). Table-cell claims excluded from the bar,
    counted and reported separately. Fixtures below the floor are excluded per PRD M4 and
    documented in `fixtures/papers/README.md` with their measured rate — never silently.
  - Span round-trip on the converted text: `text[location.start:location.end] ==
    claim.reported_value.text` (the `test_pipeline.py:66-76` pattern applied to PDF-derived
    claims).
  - Cross-process byte identity of the converted text on at least one fixture (subprocess,
    varying `PYTHONHASHSEED`).
  - Recovery accounting (PRD S1): per-paper recovery rate printed in the test output.
- Doc amendments (PRD M5): `docs/technical/CAPABILITY_ROADMAP.md` C1 status (PDF input no
  longer "Not built"; gate C1 prerequisite met), `CLAUDE.md` status line, `README.md` status
  and dependency claims, `docs/technical/ARCHITECTURE.md` only if it names a dependency
  constraint that changed.
- Suite integrity: `test_determinism.py`, `test_no_network.py`, and the whole suite stay
  green; `uv run pytest` from the repo root.

## Out-of-scope

- PageBox locations (deferred). `Location` remains `CharSpan` over the converted text.
- Changes to the pipeline, record layer, or selection rules.
- DOI resolution, BYOK proposer, C7 (PRD out-of-scope list).
- Any verdict emission.

## Acceptance criteria (test-first)

1. `tests/extract/test_pdf_seam.py` — the failing-then-passing tests for claim-id equality
   (abstract floor + whole-paper ≥ 90% floor), span round-trip, and per-paper recovery
   reporting, written before any converter code beyond what `frontend` shipped.
2. Cross-process byte-identity test on PDF-derived text passes.
3. Full suite green: `uv run pytest` (no network, determinism suites included).
4. The three doc amendments are in place and internally consistent (no file still lists PDF
   as not built).

## Dependencies & sequencing

- Requires `fixtures` (PDFs + survey floor) and `frontend` (converter).
- Last aspect in the slice.
- Consumes the sealed seam — this aspect must not need a seam change; if it does, that is a
  PRD violation to flag, not to code around.

## Open questions / risks

- A fixture that cannot clear the floor triggers PRD M4 (exclude-and-document). The test
  suite must still pass — the exclusion is a recorded, labeled state, not a failure.
- Recovery-rate arithmetic must be defined before the test is written: denominator =
  Markdown-path claims in scope (abstract section / whole paper), numerator = PDF-path
  claims recovered by id. Pin this in the plan so the test cannot be gamed by moving claims
  between buckets.