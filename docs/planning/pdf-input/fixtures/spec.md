# Aspect spec: `fixtures` — real PDF fixtures + signal survey

## Problem slice

Acceptance criteria 1–2 of `docs/planning/pdf-input/prd.md` need PDF fixtures of the five CC
BY papers; none exist anywhere locally (verified by search). This aspect sources them,
plumbs the repo for binary fixtures, and measures the reconstruction signal that sets the
recovery floor for the whole slice.

## In-scope

- Fetch the five papers' real journal PDFs from Europe PMC (authorized, read-only fetch;
  precedent `fixtures/papers/README.md:15-17`), as a dev-time tool script under `tools/`
  (e.g. `tools/fetch_pdf_fixtures.py`) that records source URLs — **never run in tests**.
- Commit the PDFs as binary fixtures under `fixtures/papers/` named `PMC*.pdf` alongside the
  existing `PMC*.md`.
- Add a `.gitattributes` binary rule for `*.pdf` (current `* text=auto eol=lf` would mangle
  them; the line-ending pinning test `tests/extract/test_determinism.py:1135-1160` must stay
  green).
- Update `fixtures/papers/README.md`: PDF sourcing, URLs, fetch date, and resolution of the
  two known DOI discrepancies between the README table and the `<!-- source -->` comments
  (PMC12780771, PMC13363872).
- **Signal survey:** on the first fetched PDF, measure (a) heading-detection recovery and
  (b) table-reconstruction recovery against the paper's Markdown, using a throwaway probe
  script. Record the numbers in the README; they set the ≥ 90% floor (PRD M3) and the
  reconstruction design for the `frontend` aspect.
- The fixture-loading convention for tests (glob `fixtures/papers/*.pdf`).

## Out-of-scope

- Any PDF parsing code (the `frontend` aspect).
- Any changes to `src/plumb/extract/`.
- Network access inside tests — the fetch and the probe run at dev time only.

## Acceptance criteria (test-first)

1. `tests/extract/test_pdf_fixtures.py` — a failing test asserting five `PMC*.pdf` fixtures
   exist and are non-trivial (size floor), written before the fetch; it passes once the
   fetch lands.
2. The `*.pdf` binary rule exists in `.gitattributes`, and `git check-attr text -- fixtures/papers/PMC*.pdf` reports the PDFs as binary/unset; `test_determinism.py` line-ending pin stays green.
3. `fixtures/papers/README.md` documents each PDF's source URL, fetch date, and the resolved
   DOI (comment wins where the README table disagreed — verified against the `<!-- source -->`
   line).
4. The signal survey numbers for the first PDF are recorded in the README (heading recovery
   rate, table recovery rate) before the `frontend` aspect's design is locked.

## Dependencies & sequencing

- First aspect in the slice: `frontend` and `seam` tests consume the PDFs.
- No dependency on `src/plumb/` code.
- Europe PMC PDF endpoint availability is the one external dependency; record URLs so a
  re-fetch is possible.

## Open questions / risks

- Publisher PDFs may render abstracts with text layering that extraction mangles — the survey
  measures this; the floor follows the measurement (PRD M4: excluded-and-documented, never a
  silent pass).
- DOI provenance: the two discrepancies are resolved by the `<!-- source -->` comments; note
  any residual disagreement in the README rather than silently picking one.