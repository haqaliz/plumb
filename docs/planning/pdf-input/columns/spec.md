# Aspect spec: `columns` — multi-column layout reconstruction

## Problem slice

The `seam` checkpoint showed the converter is single-column-oriented: pypdf's extraction
interleaves two-column content streams, so line reconstruction merges left/right fragments.
Four of five fixtures (all two-column journals — Oxford, MDPI ×2, Springer) recover only
0–28% of non-table claims and are excluded per PRD M4. The Phase 0 C1 prerequisite is
therefore met only for single-column journals. This aspect closes that gap: column-aware
reconstruction so the excluded fixtures clear the recovery floors.

## In-scope

- `src/plumb/pdf/convert.py` — column-aware reconstruction:
  - Use the visitor's text matrix (`tm`) x/y coordinates (pypdf passes `cm`, `tm`, `font_size`
    to the visitor) to classify text segments by page position.
  - Detect two-column pages: project segment x-centers and find the central gutter (a
    low-density vertical band); a page with a gutter and content on both sides is two-column.
  - Classify segments as **full-width** (spanning the gutter — title, abstract banner) or
    **column-bound**; full-width segments interrupt the column flow and are emitted in y-order
    at their position; column-bound segments are grouped per column (left then right), lines
    assembled within a column by y-proximity and sorted by x.
  - Handle page headers/footers (running heads, page numbers) deterministically — e.g. drop
    lines in the top/bottom bands or repeating across pages — with drops recorded in
    `ConversionStats`, never silent.
  - Handle the known MDPI inverted-y title quirk (PMC13298092) and the Cureus caption-below-
    table quirk without regressing the single-column path.
- `tests/pdf/test_convert.py` — unit tests for gutter detection, column grouping, full-width
  interleaving, and header/footer drops, written first.
- `tests/extract/test_pdf_seam.py` — the four excluded fixtures move from the M4-exclusion
  assertion path to the recovery-floor path (RED first, then GREEN); PMC13134363 stays at
  abstract 19/19, non-table 19/19.
- `fixtures/papers/README.md` — M4 exclusions removed for fixtures that clear; residual
  failures (if any) stay documented with new measured rates.
- `CLAUDE.md`, `README.md`, `docs/technical/CAPABILITY_ROADMAP.md` — status re-qualified to
  the true post-fix coverage (if all five clear: PDF input built including two-column; if not:
  keep the qualified wording with the remaining gap named).
- Investigate PMC12780771's pypdf tail-drop ("Exceeded 5000 form XObject invocations"): if
  pypdf exposes a way to raise the limit, use it (pinned behaviour stays deterministic); if
  not, record the residual loss honestly.

## Out-of-scope

- `PageBox` Location variant (still deferred; PRD out-of-scope).
- Any change to `src/plumb/extract/` or the seam.
- OCR / image-only PDFs, three-column layouts, RTL scripts — no fixture exercises them; do
  not design for them.
- New runtime dependencies (pypdf stays the only one).

## Acceptance criteria (test-first)

1. Each of the four previously excluded fixtures recovers **100% of abstract-section claims by
   id** and **≥ 90% of non-table whole-paper claims by id** (the seam test's pinned
   arithmetic), verified by `tests/extract/test_pdf_seam.py`.
2. PMC13134363 does not regress (abstract 19/19; non-table 19/19).
3. Column-aware unit tests: gutter detection, left-before-right ordering, full-width
   interleaving, header/footer drops counted.
4. Full suite green (`uv run pytest`), including determinism (in-process + cross-process) and
   no-network tests; conversion stays byte-identical across processes.
5. If any fixture still cannot clear a floor after honest effort, it remains M4-documented
   with the new rate — never a silent pass, never a hard fail on an honest residual.

## Dependencies & sequencing

- Requires the completed `fixtures`, `frontend`, and `seam` aspects (same worktree/branch).
- The seam tests' expectation update is the RED for the converter work.

## Open questions / risks

- Gutter detection must not misfire on single-column pages (regression risk) — the Cureus
  fixture is the control.
- pypdf's visitor may not expose coordinates for all font/encoding types; the fallback must
  preserve the current single-column behaviour rather than break it.
- Header/footer heuristics are journal-specific; prefer y-band + repetition over text
  patterns, and count drops.