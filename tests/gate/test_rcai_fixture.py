"""The RCAI gate fixture: the paper member, pinned and seam-checked (notebook-paper P1/P2a).

The paper (arXiv:2609.00137v1, CC BY 4.0) is the fixture's paper member. Per P2a the PDF is
the member unless `pdf_to_markdown` cannot place the §3/§4.2 table spans, in which case the
arXiv HTML → Markdown rendering is committed instead and the fallback is recorded in the
fixture README. This test pins whichever format actually shipped: the member's SHA-256 equals
the README's recorded pin, and the PDF seam (when the member is the PDF) places both table
token sets verbatim in the normalized text.

The 5 seated PDF fixtures' recovery floors do not move: they are asserted by the existing
`tests/extract/test_pdf_seam.py` / `tests/extract/test_pdf_fixtures.py`, untouched here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from plumb.extract.location import normalize_text
from plumb.pdf import pdf_to_markdown

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "gate" / "rcai"
PDF_SHA256 = "8ddf1e2f55f938f089517ca998a43bb22ab2baa804748c7bc860a47035b858a8"

MIN_PDF_BYTES = 100 * 1024  # 100 KiB

TABLE_3_TOKENS = ("12.90", "24.73", "11.83")
TABLE_4_2_TOKENS = ("10.40", "16.53", "6.13", "9.75", "12.58", "2.82", "8.97", "13.42", "4.45")


@pytest.fixture(scope="module")
def paper_text() -> str:
    return normalize_text(pdf_to_markdown((FIXTURE / "paper.pdf").read_bytes()))


def test_the_pdf_is_the_recorded_arxiv_file() -> None:
    data = (FIXTURE / "paper.pdf").read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) >= MIN_PDF_BYTES
    assert hashlib.sha256(data).hexdigest() == PDF_SHA256
    assert PDF_SHA256 in (FIXTURE / "README.md").read_text(encoding="utf-8")


def test_the_pdf_seam_places_the_table_tokens(paper_text: str) -> None:
    for token in TABLE_3_TOKENS + TABLE_4_2_TOKENS:
        assert token in paper_text, token
