"""`plumb corpus` — the discrepancy-corpus surface: bank a verify record as a case.

`bank_record` is the bank seam: the record is validated by the **replay chain**
(`read_record` — strict member reading, run-id check, curated claims re-admitted
against the record's own paper — then `load_bindings` + `verify_claims`
re-derivation from the stored trace, then `cross_check` against the committed
`verdicts.json`), exactly as `plumb verify --from-record` reads it. A record
that would not replay does not bank: nothing is written on any refusal. The
committed `verdicts.json` is never trusted alone — the bank re-derives first
and cross-checks.

**The bank transports, never creates.** The optional record-side `labels.json`
(human-authored) is validated against the re-admitted claim ids and transported
into the case; a malformed one is `RECORD_INVALID`. The record's
`unrepresentable.json` (the gate record's non-claim document) is staged as the
case's `nonclaims.json` **verbatim**. No labels file, no `unrepresentable.json`
→ no `labels.json`, no `nonclaims` lane.

**Staging is transient.** The lanes are copied into a `tempfile` directory
exactly as `bank_case` reads a record, so the case bytes derive from the
record's bytes only — the temp path never reaches the case. The case id is
content-addressed; a re-bank of the identical record is a no-op, a conflicting
re-bank is `CorpusRefused` (`CASE_CONFLICT`), and the existing case is never
touched.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from plumb.cli.replay import cross_check, read_record
from plumb.corpus import bank_case
from plumb.verify import Completed, load_bindings, verify_claims

__all__ = ["bank_record", "cmd_corpus_bank"]

#: The label values a human-authored review may carry; anything else is malformed.
_LABEL_VALUES = frozenset({"confirmed", "refuted"})

#: The member lanes `bank_case` reads of a record, in the order the record carries them.
_MEMBER_FILES = ("claims.json", "bindings.json", "trace.json", "verdicts.json")

_PAPER_FILES = ("paper.pdf", "paper.md")


def cmd_corpus_bank(args, parser) -> int:
    """`plumb corpus bank <record-dir> [--store DIR]`: bank, print, exit 0."""
    record_dir = Path(args.record_dir)
    if not record_dir.is_dir():
        parser.error(f"<record-dir> {args.record_dir!r} is not a directory")
    case_id, already = bank_record(record_dir, Path(args.store))
    print(f"already banked: {case_id}" if already else f"banked {case_id}")
    return 0


def bank_record(record_dir: Path, store_dir: Path) -> tuple[str, bool]:
    """Bank `record_dir` under `store_dir`; returns `(case_id, was_a_no_op)`.

    The record is validated by the replay chain before anything is written;
    `labels` are read record-side and validated; the lanes are staged in a
    transient directory and banked through `bank_case`. Nothing is banked on
    any refusal.
    """
    claims, bindings_bytes, trace, capture, _paper, _paper_format = read_record(record_dir)
    bindings = load_bindings(bindings_bytes, [c.id for c in claims])
    verdicts = verify_claims(claims, bindings, Completed(trace, capture))
    cross_check(record_dir, verdicts)
    labels = _record_labels(record_dir, {c.id for c in claims})
    with tempfile.TemporaryDirectory(prefix="plumb-corpus-") as tmp:
        staged = _stage(record_dir, Path(tmp) / "record")
        with tempfile.TemporaryDirectory(prefix="plumb-corpus-probe-") as probe:
            case = bank_case(staged, probe, labels=labels)
        already = (store_dir / case.case_id).exists()
        bank_case(staged, store_dir, labels=labels)
    return case.case_id, already


def _record_labels(record_dir: Path, claim_ids: set[str]) -> dict[str, str] | None:
    """The record's human-authored labels, validated against the re-admitted ids.

    Absent `labels.json` -> `None`: the bank transports, never creates. A
    document that is not an object, a key that is not a re-admitted claim id,
    or a value outside `{confirmed, refuted}` is `ValueError`, which the shell
    renders as `RECORD_INVALID`.
    """
    path = record_dir / "labels.json"
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"record {record_dir}: labels.json does not parse: {exc!r}"
        ) from None
    if not isinstance(document, dict):
        raise ValueError(f"record {record_dir}: labels.json must be an object")
    for claim_id, value in document.items():
        if claim_id not in claim_ids:
            raise ValueError(
                f"record {record_dir}: labels.json names unknown claim {claim_id!r}"
            )
        if value not in _LABEL_VALUES:
            raise ValueError(
                f"record {record_dir}: the label for {claim_id!r} must be one of "
                "confirmed, refuted"
            )
    return dict(document)


def _stage(record_dir: Path, staged: Path) -> Path:
    """The record's lanes under `staged`, exactly what `bank_case` reads.

    The member files, the `objects/` tree and the paper (pdf preferred, else
    markdown) are copied verbatim; the record's `unrepresentable.json`, when
    present, is written as the case's `nonclaims.json` verbatim.
    """
    staged.mkdir(parents=True)
    for name in _MEMBER_FILES:
        shutil.copyfile(record_dir / name, staged / name)
    shutil.copytree(record_dir / "objects", staged / "objects")
    for name in _PAPER_FILES:
        path = record_dir / name
        if path.is_file():
            shutil.copyfile(path, staged / name)
            break
    unrepresentable = record_dir / "unrepresentable.json"
    if unrepresentable.is_file():
        (staged / "nonclaims.json").write_bytes(unrepresentable.read_bytes())
    return staged