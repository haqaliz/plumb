# C1 PDF input — issue card

Source: inline brief (from the `plumb-next` handoff, 2026-09-22). No GitHub issue — the id is a slug.

## Brief

**C1 PDF input — the missing slice that completes C1 and is named by the Phase 0 gate
(`docs/ROADMAP.md:21`, `docs/technical/CAPABILITY_ROADMAP.md:47-49`).** Convert a paper PDF
to plain text deterministically and offline, then feed it through the existing
`extract_claims(raw)` seam (`src/plumb/extract/pipeline.py`) unchanged, so a PDF and the
equivalent Markdown yield the same claims with correct `Location` records. Caveat: PDF table
extraction fidelity is the known hard part and lands on R3 — keep the front-end deterministic,
add the smallest pure-Python, pinned, offline PDF dependency (the repo is zero-dep today), and
keep `test_no_network.py` green. Acceptance tests, written first: (1) a PDF fixture of a CC BY
paper parses to text byte-identically across processes; (2) claims extracted from the PDF equal
claims extracted from the paper's Markdown, via the existing seam; (3) `Location` records point
at real PDF page/table positions; (4) no network is reachable from any test; (5) the slice ships
with a failing-then-passing test per test-first convention.