# C1 PDF input — understanding (deep dig, 2026-09-22)

Places the unit in the codebase. Sources: agent dig of `src/plumb/extract/`, `tests/extract/`,
planning docs, and fixture provenance.

## What the work is really asking

Convert a paper PDF to plain text deterministically and offline, feed it through the existing
`extract_claims(raw)` seam (`src/plumb/extract/pipeline.py:29-61`) unchanged, so a PDF and the
equivalent Markdown yield the same claims. Completes C1 (the Phase 0 gate's C1 minimum is
"text/PDF" — `docs/ROADMAP.md:21`; `CAPABILITY_ROADMAP.md:47-49` says the gate is not met
because PDF is missing).

## The seam and its contract (verified in code)

- `extract_claims(raw: str) -> (tuple[Claim,...], tuple[Rejection,...])` — `raw` is a `str`,
  normalized once via `normalize_text` (CRLF→LF + NFC only, `location.py:26-47`); every
  `CharSpan` indexes the normalized bytes; `hash_paper` rejects `bytes` (`hashing.py:116-120`).
  So the converter must produce `str`; there is no bytes or document-object seam.
- **The "equivalent Markdown" bar is structural, not cosmetic.** Section hints come from ATX
  headings (`candidates.py:341-359`); cells come from GFM pipe tables (`tables.py:26-36`).
  Without headings, every candidate lands in `other` and `select` rejects all
  (`selection.py:446-447`). A naive PDF text dump would collapse the claim set to zero.
- Claim equality across PDF/Markdown must be by claim `id` (value text + metric + units —
  `claim.py:61-70`), not full dataclass equality: `Location` is part of the record and will
  legitimately differ between the two inputs.
- **`Location` is a single-variant union today** (`CharSpan`, `location.py:50-104`). A
  `PageBox` variant (PDF page + bbox) was deliberately pre-shaped for in the design docs
  (`claim-schema/spec.md:27`; `determinism-serialization/plan_20260921.md:71-84`) but touching
  it hits five pinned contracts: `location.py` union, `serialize.py:218-237`,
  `ordering.py:77-84`, `SERIALIZED_SCHEMA` (`test_determinism.py:592-690`), and the
  hash-anchoring invariant (`hashing.py:5-10`, where CharSpan round-trips against the hash but
  a page/bbox coordinate is not derivable from the text). This is the riskiest part of the
  brief's acceptance criterion 3 and the natural candidate for a follow-on slice.

## Test-convention constraints (verified in code)

- Autouse `_block_network` fixture in `tests/conftest.py:56-60` replaces socket primitives for
  every test; `test_no_network.py` proves it fires. The PDF dependency must not resolve
  hostnames or open sockets (at import or use).
- AST source guards in `test_determinism.py:975-1062` scan **only `src/plumb/extract/`**
  (import allowlist: `__future__, abc, collections, dataclasses, decimal, hashlib, json, plumb,
  re, typing, unicodedata`). A converter placed in a new package `src/plumb/pdf/` sidesteps the
  allowlist but inherits the network blocker and all record contracts.
- Cross-process byte-identity determinism is pinned by `test_determinism.py` (fresh
  interpreters under varying `PYTHONHASHSEED`, raw stdout bytes compared).
- A committed binary PDF fixture needs a `.gitattributes` binary/`-text` rule — the current
  `* text=auto eol=lf` (pinned by `test_determinism.py:1135-1160`) would mangle it.

## Fixture situation (the slice's first blocker)

- The five CC BY fixtures are JATS-XML-derived Markdown (`fixtures/papers/README.md:15-21`),
  sourced from Europe PMC. **No PDF of any of them exists anywhere locally** (repo, ~/dev,
  ~/Downloads, git history, Spotlight) — verified by search.
- So acceptance criterion 1 ("a PDF fixture of a CC BY paper") has no on-disk input today.
  Options: fetch the real journal PDFs from Europe PMC (authorized-fetch precedent in
  `fixtures/papers/README.md:15-17`) or generate deterministic PDFs from the Markdown
  (offline, but synthetic — they won't exercise real-world PDF layout and would weaken the
  "real PDF" value of the fixture). Sourcing the real PDFs is preferred if authorized.
- Known provenance wobble to resolve when sourcing: `<!-- source -->` DOIs disagree with the
  `fixtures/papers/README.md` table for two papers (PMC12780771, PMC13363872).

## Dependency stance

- `pyproject.toml:7` is `dependencies = []`; the "zero runtime dependencies" claim appears in
  `CLAUDE.md:25`, `CAPABILITY_ROADMAP.md:39`, `README.md:9`. Adding the smallest pure-Python,
  pinned, offline PDF dep (brief's wording) amends all three. Candidate: pypdf (pure-Python,
  BSD, no deps, no network) — but it does **no table extraction**, so heading/table
  reconstruction for the Markdown-equivalent bar would be our own heuristics (the R3 risk).
  Heavier options (pdfplumber/PyMuPDF) add deps, and PyMuPDF is AGPL — likely out.

## Open questions for the PRD interview

1. **Criterion 3 scope**: must `Location` gain a `PageBox` variant in this slice (five pinned
   contracts, hash-anchoring implications), or is criterion 3 a follow-on slice — with this
   slice keeping `CharSpan` over the converted text? The Phase 0 gate does not require
   PageBox; it requires PDF text to flow through the seam.
2. **The equality bar (criterion 2)**: compare by claim `id` (text+metric+units), not full
   records — Location fields will differ. Confirm.
3. **Fixture sourcing**: fetch real PDFs from Europe PMC (authorized, matches "real PDF" bar)
   vs generate from Markdown (offline, synthetic).
4. **Library**: pypdf (minimal, no tables → our own reconstruction) vs a table-capable dep
   (heavier). The brief's "smallest pure-Python" wording points at pypdf.
5. **Where the converter lives**: new `src/plumb/pdf/` package (outside the AST-guard scope)
   vs inside `src/plumb/extract/` (must amend the import allowlist deliberately).