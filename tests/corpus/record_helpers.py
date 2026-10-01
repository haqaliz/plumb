"""Synthetic records for the corpus store tests: real C3/C4 bytes, cheaply built.

One `record_dir(...)` call is one real verify run: `run_full` (the verify
helpers' real C3 path — a checkout, this interpreter as the entry point, the
real capture) plus C4's real binding and verdict path, serialized by the real
serializers (`serialize_trace`, `serialize_verdicts`, `serialize_claims`). The
record directory is the shape the corpus bank and `--from-record` read
(`src/plumb/cli/replay.py:96-124`): `claims.json`, `bindings.json`,
`trace.json`, `verdicts.json`, `objects/` of hash-named files, and a
`paper.md` — plus the optional `nonclaims.json` lane. No test ever hand-writes
a member that has a real serializer; the one hand-shaped document is
`nonclaims_json`, whose serialized form the bank aspect will own, mirrored
from the committed gate record's `unrepresentable.json`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "verify"))
from verify_helpers import bindings_json, claim, run_full, writes  # noqa: E402

from plumb.extract.hashing import PaperHash
from plumb.extract.serialize import serialize_claims
from plumb.run.trace import serialize_trace
from plumb.verify import Completed, serialize_verdicts, verify_claims
from plumb.verify.bindings import load_bindings

__all__ = ["DEFAULT_PAPER", "nonclaims_json", "record_dir"]

#: The paper a default record banks, unless `paper=` overrides it.
DEFAULT_PAPER = b"# Synthetic paper\n\nAUC was 0.87.\n"

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}

#: The claims lane's paper digest for a paperless record (the lane is opaque bytes).
_NO_PAPER_DIGEST = hashlib.sha256(b"plumb.corpus.test.record.no-paper").hexdigest()


def record_dir(
    root: Path,
    *,
    paper: bytes | None = DEFAULT_PAPER,
    nonclaims: bytes | None = None,
) -> Path:
    """A real record under `root/record`, from one real run of a JSON-writing program.

    `paper=None` writes no paper file, so the case banks with `paper_hash:
    null`; `nonclaims`, when given, adds the `nonclaims.json` lane. Every byte
    is the real serialized form of a real run, so the store's round-trip,
    no-op, conflict and tamper tests exercise exactly the bytes a `plumb
    verify` record would carry.
    """
    paper_claim = claim("0.87")
    _, _result, capture, trace = run_full(root, writes("results.json", '{"auc": 0.8712}'))
    bindings_bytes = bindings_json(
        (paper_claim, "results.json", {"kind": "json_pointer", "pointer": "/auc"})
    )
    bindings = load_bindings(bindings_bytes, [paper_claim.id])
    verdicts = verify_claims([paper_claim], bindings, Completed(trace, capture))

    record = root / "record"
    (record / "objects").mkdir(parents=True)
    for path in capture.store.iterdir():
        (record / "objects" / path.name).write_bytes(path.read_bytes())
    digest = hashlib.sha256(paper).hexdigest() if paper is not None else _NO_PAPER_DIGEST
    (record / "claims.json").write_bytes(
        serialize_claims([paper_claim], paper_hash=PaperHash(digest=digest))
    )
    (record / "bindings.json").write_bytes(bindings_bytes)
    (record / "trace.json").write_bytes(serialize_trace(trace))
    (record / "verdicts.json").write_bytes(serialize_verdicts(verdicts))
    if paper is not None:
        (record / "paper.md").write_bytes(paper)
    if nonclaims is not None:
        (record / "nonclaims.json").write_bytes(nonclaims)
    return record


def nonclaims_json() -> bytes:
    """The non-claims lane in the committed gate record's shape (unrepresentable.json)."""
    document = {
        "unrepresentable": [
            {
                "section": "4.1",
                "text": "p < 0.001",
                "context": "(F = 145.33, p < 0.001)",
                "start": 100,
                "end": 109,
                "reason": "the paper's own text is not a parseable bound",
            },
        ]
    }
    return (json.dumps(document, **_JSON) + "\n").encode("utf-8")