# Aspect spec: `frontend` — the PDF→Markdown converter

## Problem slice

The C1 seam (`extract_claims(raw: str)`, `src/plumb/extract/pipeline.py:29-61`) accepts a
`str` only, normalized by `normalize_text` (CRLF→LF + NFC; **no whitespace collapsing** —
`src/plumb/extract/location.py:26-47`). A PDF must become Markdown-equivalent text: ATX
headings (section hints — `candidates.py:341-359`) and GFM pipe tables (`tables.py:26-36`);
without headings every candidate lands in `other` and selection rejects all
(`selection.py:446-447`). This aspect builds that converter deterministically, offline, on
the smallest pinned pure-Python dependency (pypdf, per the approved PRD).

## In-scope

- `src/plumb/pdf/` package — deliberately **outside** `src/plumb/extract/` so the
  deterministic-core AST import allowlist (`test_determinism.py:1048-1062`) is not amended.
- `pypdf` pinned exactly in `pyproject.toml` (`dependencies = []` today — `pyproject.toml:7`).
- `pdf_to_markdown(pdf_bytes: bytes) -> str`:
  - Deterministic for fixed input bytes; zero network I/O at import or parse.
  - Heading reconstruction via pypdf's font-size visitor; falls back to a named heuristic
    (line-shape/TOC-like rules) when font signals are absent — never silent flat text.
  - Pipe-table reconstruction via deterministic layout heuristics on line runs; tables that
    fail to reconstruct are dropped with a recorded count (surfaced in the return or a
    side-channel the seam tests can report), never silently merged into prose.
  - **Line-joining rule for value-bearing text:** join wrapped lines inside numeric tokens
    (e.g. `0.0` + newline + `3` → `0.03`) because `normalize_text` will not collapse the
    whitespace and a split value changes the claim id vs the Markdown path (PRD gap 2).
  - The `# Title` H1 and `<!-- source -->`-style first line: emit a title line so H1-level
    context survives; exact fixture-parity is decided by the seam tests, not guessed here.
- The no-network property: the module and pypdf must not touch sockets/hostnames (autouse
  blocker `tests/conftest.py:56-60`; `test_no_network.py` stays green).

## Out-of-scope

- `PageBox` Location variant (deferred; PRD out-of-scope).
- Any change to `src/plumb/extract/` or the seam signature.
- Verdicts, binding, anything beyond text production.
- Table extraction quality guarantees: reconstruction is heuristic; the recovery floor and
  exclusion policy live in the `seam` aspect (PRD M4).

## Acceptance criteria (test-first)

1. `pdf_to_markdown` on a PDF fixture returns a `str` that round-trips through
   `extract_claims` without error and whose output contains `##` headings (assert on the
   converted text directly).
2. Determinism: converting the same fixture bytes in fresh interpreters (varying
   `PYTHONHASHSEED`, subprocess — the `test_determinism.py` pattern) yields byte-identical
   output.
3. No-network: the suite (including `test_no_network.py`) stays green; the converter is
   exercised under the autouse blocker.
4. Value line-join: a crafted fixture (or unit-level case) with a value split across a line
   break converts to the unsplit token.
5. `pyproject.toml` pins pypdf exactly; `uv.lock` updated via `uv add`.

## Dependencies & sequencing

- Requires the `fixtures` aspect (PDFs on disk, survey numbers informing the reconstruction
  design and the floor).
- Independent of `seam`; produces the converter the seam tests consume.
- Zero deps on the rest of the engine.

## Open questions / risks

- R3 (claim-extraction error) is the operative risk: reconstruction heuristics can mangle
  numbers. The admission gate downstream catches ungrounded candidates, but the converter
  must prefer dropping a doubtful token to emitting a plausible wrong one (drop-and-count,
  never invent).
- Journal-specific font encodings may defeat size-based heading detection — the fallback
  path is in scope, and its coverage is measured by the seam aspect's recovery rate.
- pypdf is pinned by version; a future pypdf release changing extraction output would change
  byte identity — the pin is what makes the determinism claim honest.