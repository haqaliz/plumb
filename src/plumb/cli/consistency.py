"""`plumb consistency <paper>` — C7's surface, labeled as the weaker signal it is.

Exit contract: 0 when no internal inconsistency was found (including a paper with nothing
checkable), 1 when at least one was, 2 on usage. It never prints a verdict and never runs code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from plumb.cli.live import _read_paper
from plumb.consistency import ConsistencyReport, check_consistency

__all__ = ["cmd_consistency"]

_JSON = {"sort_keys": True, "ensure_ascii": False, "separators": (",", ":")}


def cmd_consistency(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Check the paper at `<paper>`; report every finding, exit 1 on any inconsistency."""
    from plumb.cli import PAPER_UNREADABLE, PaperUnreadable

    try:
        raw, _format, text = _read_paper(Path(args.paper))
    except PaperUnreadable as exc:
        print(f"plumb consistency: {PAPER_UNREADABLE}: {exc}", file=sys.stderr)
        return 1
    report = check_consistency(text)
    if args.json:
        document = {
            "paper_sha256": hashlib.sha256(raw).hexdigest(),
            "counts": report.counts(),
            "findings": [
                {
                    "kind": f.kind, "label": f.label, "reported": f.reported,
                    "detail": f.detail, "span": [f.span.start, f.span.end],
                }
                for f in report.findings
            ],
        }
        print(json.dumps(document, **_JSON))
    else:
        sys.stdout.write(_render(report))
        sys.stdout.flush()
    return 1 if report.inconsistent else 0


def _render(report: ConsistencyReport) -> str:
    counts = report.counts()
    lines = [
        "This is an internal-consistency check, not a reproduction verdict: "
        "an inconsistency is the paper's numbers disagreeing with each other.",
        "",
        f"{'KIND':<10} | {'LABEL':<22} | WHAT",
    ]
    for finding in report.findings:
        lines.append(
            f"{finding.kind:<10} | {finding.label:<22} | {finding.reported} — {finding.detail}"
        )
    lines += [
        "",
        f"inconsistencies: {counts['INTERNAL_INCONSISTENCY']}  "
        f"consistent: {counts['CONSISTENT']}  "
        f"not applicable: {counts['NOT_APPLICABLE']}",
    ]
    return "\n".join(lines) + "\n"
