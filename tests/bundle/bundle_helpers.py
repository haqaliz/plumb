"""A tiny paper, a real C3 run of a local program, and its claims — for bundle tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.value import parse_value
from plumb.intake.checkout import SourceRecord, resolve_local
from plumb.intake.env import EnvBuild
from plumb.run import EntryPoint, run_and_capture

PAPER = "# Results\n\nThe model reached an AUC of 0.87 and an F1 of 0.91 (p < 0.001).\n"
TEXT = normalize_text(PAPER)
OLD = 1_000_000_000
PROGRAM = (
    "import json, sys\n"
    "json.dump({'auc': 0.8712, 'f1': 0.95}, open('results.json', 'w'))\n"
    "print('p = 0.0004')\n"
    "sys.stderr.write('warning: secret-token\\n')\n"
)


def claim(text: str, metric: str) -> Claim:
    start = TEXT.index(text)
    return Claim(parse_value(text), None, metric, CharSpan(start, start + len(text)), None, None)


CLAIMS = [claim("0.87", "AUC"), claim("0.91", "F1"), claim("p < 0.001", "p-value")]


def bindings_bytes(claims=CLAIMS) -> bytes:
    targets = {
        "AUC": ("results.json", {"kind": "json_pointer", "pointer": "/auc"}),
        "F1": ("results.json", {"kind": "json_pointer", "pointer": "/f1"}),
        "p-value": ("<stdout>", {"kind": "stdout_regex", "pattern": r"p = (\S+)"}),
    }
    return json.dumps({"bindings": [
        {"claim_id": c.id, "artifact": targets[c.metric][0], "locator": targets[c.metric][1],
         "float_repr": targets[c.metric][0] != "<stdout>"}
        for c in claims
    ]}).encode()


def real_run(tmp_path: Path, extra_files: dict[str, bytes] | None = None):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# demo\n")
    for rel, data in (extra_files or {}).items():
        (root / rel).write_bytes(data)
    for path in root.iterdir():
        os.utime(path, (OLD, OLD))
    checkout = resolve_local(root)
    entry = EntryPoint(argv=("python", "-c", PROGRAM), source="explicit")  # no local path
    build = EnvBuild(ok=True, policy="best-effort", detail="stub")
    trace, capture = run_and_capture(checkout, build, entry, run_dir=tmp_path / "run")
    return checkout, trace, capture


SOURCE = SourceRecord(
    kind="git", location="https://example.org/demo.git", rev_requested="v1",
    rev_resolved="0" * 40, rev_defaulted=False, size_cap_bytes=1 << 30,
)
