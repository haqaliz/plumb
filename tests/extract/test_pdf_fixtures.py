"""The five CC BY papers must ship with real journal PDFs.

The `frontend` aspect rebuilds each paper's structure from a real PDF, so the PDFs
must exist as fixtures before that design is locked: five `PMC*.pdf` files, one per
paper, each non-trivial. They are fetched once at dev time from Europe PMC
(`tools/fetch_pdf_fixtures.py`, never imported by tests); tests never reach the
network (autouse blocker in `tests/conftest.py`), so these files are the entire
input surface the PDF pipeline will ever see in tests.
"""

from __future__ import annotations

from pathlib import Path

KNOWN_PMCIDS = (
    "PMC12780771",
    "PMC13134363",
    "PMC13298092",
    "PMC13332965",
    "PMC13363872",
)

MIN_PDF_BYTES = 10 * 1024  # 10 KiB


def pdf_fixtures() -> dict[str, Path]:
    """Map PMCID to its PDF path for the five fixture papers."""
    return {pmcid: Path(f"fixtures/papers/{pmcid}.pdf") for pmcid in KNOWN_PMCIDS}


class TestTheFivePaperPDFsExist:
    def test_all_five_pmcids_have_a_pdf(self) -> None:
        missing = [p for p in pdf_fixtures().values() if not p.is_file()]
        assert not missing, (
            "every CC BY paper must ship a PDF fixture; missing: "
            + ", ".join(str(p) for p in missing)
        )

    def test_the_fixture_set_matches_the_readme(self) -> None:
        found = sorted(p.name for p in Path("fixtures/papers").glob("PMC*.pdf"))
        assert found == [f"{pmcid}.pdf" for pmcid in KNOWN_PMCIDS]

    def test_every_pdf_is_non_trivial(self) -> None:
        small = [
            str(p)
            for p in pdf_fixtures().values()
            if p.is_file() and p.stat().st_size < MIN_PDF_BYTES
        ]
        assert not small, (
            f"PDF fixtures must be >= {MIN_PDF_BYTES} bytes; too small: "
            + ", ".join(small)
        )