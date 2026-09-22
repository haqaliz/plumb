#!/usr/bin/env python3
"""Dev-time signal survey: how much of one paper's Markdown survives in its PDF.

Measures the reconstruction floor for the `frontend` aspect on one chosen paper
(default PMC13134363 — the largest abstract label set): how many of the Markdown's
level-2 section headings can be recognized in the PDF's per-page text, and how much
of the Markdown's pipe tables has a recognizable counterpart, plus a note on whether
pypdf's per-page text output preserves the abstract prose readably.

Dev-time probe only — never imported by tests, never run in CI. Uses `pypdf` as a
throwaway dependency (the `frontend` aspect will pin it as a runtime dependency):

    uv run --with pypdf python tools/pdf_signal_survey.py [PMCID]

The reported numbers are the recovery floor for whole-paper reconstruction (PRD M3).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPERS = ROOT / "fixtures" / "papers"

try:
    from pypdf import PdfReader
except ImportError as error:  # pragma: no cover - dev tool, clear usage error
    sys.exit(
        "pypdf is not installed; run this probe as "
        "`uv run --with pypdf python tools/pdf_signal_survey.py`"
        f"\n({error})"
    )

DEFAULT_PMCID = "PMC13134363"

_SQUEEZE = re.compile(r"\s+")


def squeeze(text: str) -> str:
    """Lowercase and collapse every run of whitespace to one space."""
    return _SQUEEZE.sub(" ", text).strip().lower()


def load_pdf_text(pmcid: str) -> list[str]:
    """Per-page extracted text for one paper's PDF."""
    path = PAPERS / f"{pmcid}.pdf"
    if not path.is_file():
        sys.exit(f"no PDF at {path}; run tools/fetch_pdf_fixtures.py first")
    reader = PdfReader(str(path))
    return [(page.extract_text() or "") for page in reader.pages]


def markdown_headings(markdown: str) -> list[str]:
    """Level-2 section heading texts (`## ` lines), in order, as written."""
    return [
        line.strip()[3:].strip()
        for line in markdown.splitlines()
        if line.startswith("## ")
    ]


def markdown_table_lines(markdown: str) -> list[list[str]]:
    """Pipe-table data rows as cell lists (separator rows dropped)."""
    cells: list[list[str]] = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        row = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in row if c):
            continue
        cells.append([c for c in row if c])
    return cells


def heading_recovery(headings: list[str], pdf_text: str) -> tuple[int, int]:
    """(recovered, total) unique heading texts found in the PDF text."""
    unique = {squeeze(h) for h in headings}
    recovered = {h for h in unique if h and h in pdf_text}
    return len(recovered), len(unique)


def table_recovery(rows: list[list[str]], pdf_text: str) -> dict[str, object]:
    """Per-cell and per-line recovery of the Markdown pipe tables."""
    min_cell = 3  # ignore sub-3-char cells: they match anywhere and inflate the rate
    total_cells = recovered_cells = 0
    lines = lines_any = lines_majority = 0
    for row in rows:
        line_cells = [c for c in row if len(squeeze(c)) >= min_cell]
        if not line_cells:
            continue
        lines += 1
        hit = sum(1 for c in line_cells if squeeze(c) in pdf_text)
        total_cells += len(line_cells)
        recovered_cells += hit
        lines_any += 1 if hit else 0
        lines_majority += 1 if hit * 2 >= len(line_cells) else 0
    return {
        "cell_rate": recovered_cells / total_cells if total_cells else 0.0,
        "cells": f"{recovered_cells}/{total_cells}",
        "line_any_rate": lines_any / lines if lines else 0.0,
        "lines_any": f"{lines_any}/{lines}",
        "line_majority_rate": lines_majority / lines if lines else 0.0,
        "lines_majority": f"{lines_majority}/{lines}",
    }


def abstract_note(pages: list[str], markdown: str) -> str:
    """Whether the abstract's opening prose survives in a page's extracted text."""
    # The JATS->Markdown conversion glues the "Abstract" label to the prose
    # ("AbstractThis review..."); strip the label before matching.
    prose = markdown.split("## Abstract", 1)[1].split("## ", 1)[0].strip()
    prose = re.sub(r"^abstract", "", prose, flags=re.IGNORECASE).strip()
    opening = prose[:120]
    for index, page in enumerate(pages):
        if squeeze(opening) in squeeze(page):
            return (
                f"abstract readable: yes (opening prose found verbatim on page "
                f"{index + 1})"
            )
    return "abstract readable: NO (opening prose not found verbatim on any page)"


def survey(pmcid: str) -> None:
    pages = load_pdf_text(pmcid)
    markdown = (PAPERS / f"{pmcid}.md").read_text(encoding="utf-8")
    pdf_text = squeeze("\n".join(pages))

    headings = markdown_headings(markdown)
    heading_recovered, heading_total = heading_recovery(headings, pdf_text)
    rows = markdown_table_lines(markdown)
    tables = table_recovery(rows, pdf_text)

    print(f"Signal survey: {pmcid} (probe: tools/pdf_signal_survey.py)")
    print(f"  PDF pages:            {len(pages)}")
    print(f"  PDF text chars:       {sum(len(p) for p in pages)} (per-page, raw)")
    print(f"  Markdown ## headings: {len(headings)} lines, {heading_total} unique")
    print(
        f"  Heading recovery:     {heading_recovered}/{heading_total} "
        f"({heading_recovered / heading_total:.3f})"
    )
    print(
        f"  Table cells:          {tables['cells']} recovered "
        f"(cell rate {tables['cell_rate']:.3f})"
    )
    print(
        f"  Table lines (>=1 cell): {tables['lines_any']} "
        f"(line rate {tables['line_any_rate']:.3f})"
    )
    print(
        f"  Table lines (majority): {tables['lines_majority']} "
        f"(line rate {tables['line_majority_rate']:.3f})"
    )
    print(f"  {abstract_note(pages, markdown)}")
    abstract_pages = [
        i + 1 for i, page in enumerate(pages) if "abstract" in squeeze(page)
    ]
    print(f"  Pages mentioning abstract: {abstract_pages}")
    first = next((p for p in pages if squeeze(p).strip()), "")
    print(f"  First-page snippet:  {squeeze(first)[:300]!r}")


if __name__ == "__main__":
    survey(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PMCID)