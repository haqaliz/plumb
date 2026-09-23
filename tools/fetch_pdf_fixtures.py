#!/usr/bin/env python3
"""Dev-time fetcher for the five PDF fixtures (NEVER imported by tests).

Downloads the five CC BY papers' real journal PDFs from the PMC Open Access
subset's cloud dataset (AWS `pmc-oa-opendata`, the same OA corpus Europe PMC
serves) into `fixtures/papers/PMC<id>.pdf`, prints a manifest, and exits
non-zero if any paper fails (per-paper failures are reported and skipped).

This is a dev-time tool, run by hand. Tests must never import it and never
touch the network (`tests/conftest.py` blocks sockets; this script is the
one-time, authorized fetch that produced the committed fixtures).

Endpoint note (2026-09-22): the canonical Europe PMC PDF URLs recorded in
`fixtures/papers/README.md` (`https://europepmc.org/articles/PMC<id>?pdf=render`)
were Cloudflare-challenged from this machine (HTTP 403 "Just a moment..." for
every path, with and without a browser User-Agent), and `pmc.ncbi.nlm.nih.gov`
serves a JavaScript proof-of-work gate for its `/pdf/` route. The PMC OA
cloud dataset (`https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/`) exposes the same
publisher PDFs as plain HTTPS objects with no interactive gate, so it is the
byte source; the README records both URLs per paper.

Usage:
    uv run tools/fetch_pdf_fixtures.py
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

PMCIDS = (
    "PMC12780771",
    "PMC13134363",
    "PMC13298092",
    "PMC13332965",
    "PMC13363872",
)

OA_BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
MIN_BYTES = 10 * 1024  # 10 KiB, the fixture-test floor

ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = ROOT / "fixtures" / "papers"

_USER_AGENT = "plumb-dev-fetch/0.1 (one-time authorized fixture fetch)"


def get(url: str) -> bytes:
    """GET a URL, following redirects, with a polite User-Agent."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def list_objects(prefix: str, delimiter: str | None = None) -> list[str]:
    """List S3 keys and common prefixes under a prefix via ListObjectsV2."""
    keys: list[str] = []
    token = None
    while True:
        url = f"{OA_BUCKET}/?list-type=2&prefix={prefix}"
        if delimiter:
            url += f"&delimiter={delimiter}"
        if token:
            url += f"&continuation-token={token}"
        root = ET.fromstring(get(url))
        ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
        for key in root.iter(f"{ns}Key"):
            keys.append(key.text or "")
        for cprefix in root.iter(f"{ns}Prefix"):
            keys.append(cprefix.text or "")
        token_el = root.find(f"{ns}NextContinuationToken")
        truncated = root.find(f"{ns}IsTruncated")
        if truncated is None or truncated.text != "true" or token_el is None:
            return keys
        token = token_el.text


def resolve_pdf_url(pmcid: str) -> str | None:
    """Find the article version's PDF object key, or None if unavailable."""
    version_prefixes = [
        p for p in list_objects(f"{pmcid}.", delimiter="/")
        if p.startswith(f"{pmcid}.") and p.endswith("/")
    ]
    if not version_prefixes:
        return None
    for prefix in sorted(version_prefixes):
        for key in list_objects(prefix):
            if key.startswith(pmcid) and key.endswith(".pdf"):
                return f"{OA_BUCKET}/{key}"
    return None


def fetch_paper(pmcid: str) -> dict[str, object]:
    """Download one paper's PDF; raise with a message on failure."""
    pdf_url = resolve_pdf_url(pmcid)
    if pdf_url is None:
        raise RuntimeError("no PDF object found in the OA dataset")
    data = get(pdf_url)
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"not a PDF (first bytes {data[:8]!r})")
    if len(data) < MIN_BYTES:
        raise RuntimeError(f"PDF too small ({len(data)} bytes < {MIN_BYTES})")
    dest = DEST_DIR / f"{pmcid}.pdf"
    dest.write_bytes(data)
    return {
        "pmcid": pmcid,
        "url": pdf_url,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main() -> int:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    fetch_date = datetime.now(timezone.utc).date().isoformat()
    failures = 0
    print(f"Fetch date (UTC): {fetch_date}")
    print(f"Destination:      {DEST_DIR}")
    print("Manifest:")
    for pmcid in PMCIDS:
        try:
            manifest = fetch_paper(pmcid)
        except Exception as error:  # noqa: BLE001 - report and continue per paper
            print(f"  {pmcid}: ERROR - {error}")
            failures += 1
            continue
        print(
            f"  {manifest['pmcid']}: {manifest['bytes']} bytes, "
            f"sha256 {manifest['sha256']}, from {manifest['url']}"
        )
    if failures:
        print(f"{failures} paper(s) failed; see errors above.")
        return 1
    print("All five PDFs fetched and validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())