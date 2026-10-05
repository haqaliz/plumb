"""Live record writer: assemble a replayable record dir from live-spine materials.

`write_record(record_dir, ...)` is the writer half of the bank seam
(`docs/planning/cross-paper-coverage/bank-flag/plan_20261002.md`, Phase 2): it
takes what the live spine has in hand after `verify_claims` — the C1 claims,
the bindings bytes, the C3 trace and capture, and the paper — and writes a
record dir that `read_record` (`src/plumb/cli/replay.py:96-124`) replays
byte-identically through `load_bindings` → `verify_claims` → `cross_check`,
the same chain the corpus bank runs.

**The writer re-derives the verdicts it commits.** `verdicts.json` is
`serialize_verdicts(verify_claims(...))` over the given materials — the record
never carries verdicts it did not derive itself, the same rule `build_bundle`
holds (`src/plumb/bundle/build.py:78`).

**`objects/` carries exactly `Capture.locatable`.** stderr is captured by C3
for diagnosis and marked `diagnostic_only` (`src/plumb/run/capture.py:109-112`)
and is **never copied** — no claim may ever bind to it, and it may carry local
paths. Locatable outputs are the run's own fresh artifacts, copied verbatim by
content address; a run whose own output embeds a path would say so in its own
bytes (the pinned invariant this module keeps is stderr-free records, plus
"nothing outside `record_dir` is ever written").

**`claims.json` is the serialized C1 form** — `serialize_claims` under
`hash_paper` of the paper's own text, the same call `build_bundle` makes —
which the dual-form read (`replay.py:160-167`) reads back through
`parse_claims` and re-admits through `readmit`.

Every byte is one of the house serializers or the verbatim input; nothing here
re-spells canonical JSON. No labels, no nonclaims, no `environment.txt` or
`source.json` in this phase. Nothing outside `record_dir` is ever written.
"""

from __future__ import annotations

from pathlib import Path
import shutil

from plumb.bundle.verify import PAPER_MEMBERS, paper_text
from plumb.extract.hashing import hash_paper
from plumb.extract.serialize import serialize_claims
from plumb.run.trace import serialize_trace
from plumb.verify import Completed, load_bindings, serialize_verdicts, verify_claims

__all__ = ["write_record"]


def write_record(
    record_dir: Path,
    *,
    claims,
    bindings_bytes: bytes,
    trace,
    capture,
    paper_bytes: bytes,
    paper_format: str,
) -> Path:
    """Write the replayable record of a live run under `record_dir`; return it.

    The members are `claims.json` (the serialized C1 form under `hash_paper`
    of the paper's text), `bindings.json` (verbatim), `trace.json`, the
    re-derived `verdicts.json`, `objects/` (one hash-named file per
    `capture.locatable` artifact, copied from the capture store), and the
    paper as `paper.pdf` or `paper.md` by `paper_format`.
    """
    claims = list(claims)
    raw = paper_text(paper_bytes, paper_format)
    record_dir.mkdir(parents=True)
    (record_dir / "objects").mkdir()
    (record_dir / "claims.json").write_bytes(
        serialize_claims(claims, paper_hash=hash_paper(raw))
    )
    (record_dir / "bindings.json").write_bytes(bindings_bytes)
    (record_dir / "trace.json").write_bytes(serialize_trace(trace))
    verdicts = verify_claims(
        claims, load_bindings(bindings_bytes, [c.id for c in claims]), Completed(trace, capture)
    )
    (record_dir / "verdicts.json").write_bytes(serialize_verdicts(verdicts))
    for artifact in capture.locatable:
        shutil.copyfile(capture.store / artifact.sha256, record_dir / "objects" / artifact.sha256)
    (record_dir / PAPER_MEMBERS[paper_format]).write_bytes(paper_bytes)
    return record_dir