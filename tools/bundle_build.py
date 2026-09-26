#!/usr/bin/env python3
"""Build and sign the AgroDesign bundle from the committed gate record (signed-bundle B5).

Offline. Reads `fixtures/gate/agrodesign/` — the paper, the curated claims (re-admitted against
the paper through the gate), the bindings, the trace and the captured outputs — and writes a
signed bundle to `bundles/agrodesign/` with `plumb.bundle.build_bundle`, which re-derives the
verdicts and refuses to sign anything that would not verify.

The paper is included: it is CC BY 4.0 and a verifier needs it to ground the claims.

Signing key: the project's dedicated `plumb-bundle` Ed25519 key, which lives outside the repo
(default `~/.ssh/plumb_bundle_ed25519`); only its public key is committed, as
`bundles/allowed_signers`. Run by hand: ``uv run tools/bundle_build.py [key_path]``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from plumb.bundle import SshSigner, build_bundle, verify_bundle
from plumb.extract.admit import NonClaim, admit
from plumb.extract.candidates import SECTION_OTHER, Candidate
from plumb.extract.location import CharSpan, normalize_text
from plumb.intake.checkout import SourceRecord
from plumb.pdf import pdf_to_markdown
from plumb.run import parse_trace
from plumb.run.capture import Capture

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "fixtures" / "gate" / "agrodesign"
OUT = ROOT / "bundles" / "agrodesign"
ALLOWED = ROOT / "bundles" / "allowed_signers"
DEFAULT_KEY = Path.home() / ".ssh" / "plumb_bundle_ed25519"

SOURCE = SourceRecord(
    kind="git",
    location="https://github.com/DeepStatistix/AgroDesign.git",
    rev_requested="v1.0.1",
    rev_resolved="18b7c29a4f8de3dc9260b9fa42849e5a74097825",
    rev_defaulted=False,
    size_cap_bytes=1 << 30,
)
PAPER_SOURCE = "https://arxiv.org/pdf/2603.09041v1"


def admitted_claims(text: str):
    """The gate's curated claims, admitted through the gate at their recorded spans."""
    claims = []
    for e in json.loads((RECORD / "claims.json").read_text(encoding="utf-8"))["claims"]:
        candidate = Candidate(text=e["text"], span=CharSpan(e["start"], e["end"]),
                              context=e["context"], section_hint=SECTION_OTHER)
        result = admit(candidate, normalized_text=text, metric=e["metric"])
        if isinstance(result, NonClaim):
            raise SystemExit(f"curated claim {e['metric']!r} does not admit: {result.cause}")
        claims.append(result)
    return claims


def main() -> int:
    key = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_KEY
    if OUT.exists():
        print(f"{OUT} exists; remove it to rebuild", file=sys.stderr)
        return 1
    paper = (RECORD / "paper.pdf").read_bytes()
    text = normalize_text(pdf_to_markdown(paper))
    claims = admitted_claims(text)
    trace = parse_trace((RECORD / "trace.json").read_bytes())
    capture = Capture(store=RECORD / "objects", artifacts=trace.artifacts, stale=trace.stale,
                      causes=trace.causes)
    build_bundle(
        OUT, claims=claims, paper=paper, paper_format="pdf", paper_source=PAPER_SOURCE,
        include_paper=True, bindings=(RECORD / "bindings.json").read_bytes(), trace=trace,
        capture=capture, environment=(RECORD / "environment.txt").read_text(encoding="utf-8"),
        source=SOURCE, signer=SshSigner(key, "plumb-bundle"),
    )
    report = verify_bundle(OUT, allowed_signers=ALLOWED, principal="plumb-bundle")
    print("verified" if report.ok else f"NOT verified: {report.causes}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
