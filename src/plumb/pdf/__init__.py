"""PDF input: deterministic PDF-to-Markdown conversion on pinned pypdf.

This package is deliberately outside `src/plumb/extract/` — the deterministic core's
AST import allowlist (`tests/extract/test_determinism.py`) is not amended by its
existence. It inherits the same contracts: no network anywhere (the autouse blocker
in `tests/conftest.py` covers it, and `tests/pdf/test_convert.py` scans this
package's source for network-capable names), and the only runtime dependency is the
pinned pure-Python `pypdf` (`pyproject.toml`).

The converter emits Markdown-equivalent text for the C1 seam (`extract_claims`):
ATX headings from font-size signals, GFM pipe tables from line-run geometry, and a
numeric line-join rule so a value split across a wrapped line keeps its identity
after `normalize_text` (which does not collapse whitespace). Everything is a pure
function over the extracted runs — no randomness, no clocks, no cwd or temp
dependence — so identical input bytes give identical output text in every process
(asserted cross-process under varying `PYTHONHASHSEED`).

Nothing here emits a verdict. A PDF that cannot be read is a harness-side failure
(`PdfInputError`) — downstream, that resolves to `UNVERIFIED` with a named cause.
"""

from plumb.pdf.convert import (
    ConversionStats,
    PdfInputError,
    pdf_to_markdown,
    pdf_to_markdown_with_stats,
)

__all__ = [
    "ConversionStats",
    "PdfInputError",
    "pdf_to_markdown",
    "pdf_to_markdown_with_stats",
]