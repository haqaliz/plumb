"""The write-once case store: bank a record, read a case, refuse mutation (Phase 2).

`bank_case(record_dir, store_dir)` banks one record directory — the shape the
corpus bank and `--from-record` read (`cli/replay.py:96-124`): the required
member lanes (`claims`, `bindings`, `trace`, `verdicts`), the optional
`nonclaims` lane, `objects/`, and an optional paper file — as a case under
`<store_dir>/<case_id>/`. Member bytes are written as-is, never re-serialized;
`case.json` is the last file written, and a new case whose write fails
verification is cleaned up — it was never a case.

**Write-once.** A re-bank whose `case_id` already exists is either a no-op
(the existing case re-reads byte-for-byte as this record) or a refusal
(`CASE_CONFLICT`): the existing case is never touched. `read_case(case_dir)`
returns the manifest and every member's bytes only after verifying each one
against its manifest hash — a mismatch is `CASE_TAMPERED`, never forged bytes
returned. Labels are human annotations outside the identity and never written
by this aspect; `has_labels` is always `false`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from plumb.corpus.case import (
    FORMAT,
    REQUIRED_MEMBER_KEYS,
    Case,
    derive_case_id,
    hash_bytes,
    objects_tree_hash,
    parse_case,
    serialize_case,
)
from plumb.corpus.causes import CASE_CONFLICT, CASE_INVALID, CASE_TAMPERED, CorpusRefused
from plumb.run.trace import parse_trace

__all__ = ["CaseRead", "bank_case", "read_case"]

_PAPER_FILES = ("paper.pdf", "paper.md")


@dataclass(frozen=True)
class CaseRead:
    """A case read back: the manifest and every member's verified bytes."""

    case: Case
    members: dict[str, bytes]  # bare member keys ("claims", ...), as the manifest lists
    objects: dict[str, bytes]  # sha256 -> bytes, one entry per stored object
    paper: bytes | None


def bank_case(record_dir: Path | str, store_dir: Path | str) -> Case:
    """Bank the record at `record_dir` under `store_dir`, write-once.

    Returns the fresh `Case`. A re-bank of the identical record is a no-op; a
    re-bank whose `case_id` exists but whose stored bytes do not match the
    record is `CASE_CONFLICT`, and the existing case is never touched. A
    malformed record, or a new case whose write fails, is `CASE_INVALID`.
    """
    record = Path(record_dir)
    members = _record_members(record)
    objects = _record_objects(record)
    paper = _record_paper(record)
    case = _derive_case(members, objects, paper)
    case_dir = Path(store_dir) / case.case_id
    if case_dir.exists():
        _reject_conflict(case_dir, case)
        return case
    _write_new_case(case_dir, members, objects, paper, case)
    return case


def read_case(case_dir: Path | str) -> CaseRead:
    """The case at `case_dir`, every member verified against its manifest hash.

    A member whose bytes do not match the manifest is `CASE_TAMPERED` — its
    bytes are never returned; a missing member or an unreadable manifest is
    `CASE_INVALID`.
    """
    case_dir = Path(case_dir)
    try:
        case = parse_case((case_dir / "case.json").read_bytes())
    except (OSError, ValueError) as exc:
        raise CorpusRefused(
            f"case at {case_dir} has no readable manifest: {exc}", CASE_INVALID
        ) from None
    members: dict[str, bytes] = {}
    for key, digest in case.member_hashes.items():
        path = case_dir / f"{key}.json"
        try:
            data = path.read_bytes()
        except OSError:
            raise CorpusRefused(
                f"case {case.case_id} is missing {key}.json", CASE_INVALID
            ) from None
        if hash_bytes(data) != digest:
            raise CorpusRefused(
                f"case {case.case_id} member {key} does not match its manifest hash",
                CASE_TAMPERED,
            )
        members[key] = data
    return CaseRead(
        case=case,
        members=members,
        objects=_case_objects(case_dir, case),
        paper=_case_paper(case_dir, case),
    )


def _reject_conflict(case_dir: Path, fresh: Case) -> None:
    """Refuse a re-bank whose existing case is not byte-for-byte this record.

    The existing case is re-read through the same hash-verified path as
    `read_case`, and any mismatch — a tampered member, a different manifest —
    refuses the bank without touching the existing case.
    """
    try:
        existing = read_case(case_dir).case
    except CorpusRefused as exc:
        raise CorpusRefused(
            f"case {fresh.case_id} already exists but its bytes do not match "
            f"the record: {exc.cause}",
            CASE_CONFLICT,
        ) from None
    if existing != fresh:
        raise CorpusRefused(
            f"case {fresh.case_id} already exists with a different manifest",
            CASE_CONFLICT,
        )


def _write_new_case(
    case_dir: Path,
    members: dict[str, bytes],
    objects: dict[str, bytes],
    paper: tuple[str, bytes] | None,
    case: Case,
) -> None:
    """Write the case, verify the write, and clean up anything partial on failure."""
    try:
        for key in sorted(members):
            _write_member(case_dir / f"{key}.json", members[key])
        for digest, data in sorted(objects.items()):
            _write_member(case_dir / "objects" / digest, data)
        if paper is not None:
            _write_member(case_dir / paper[0], paper[1])
        _write_member(case_dir / "case.json", serialize_case(case))
        read_case(case_dir)
    except Exception as exc:
        shutil.rmtree(case_dir, ignore_errors=True)
        detail = exc.cause if isinstance(exc, CorpusRefused) else f"{type(exc).__name__}: {exc}"
        raise CorpusRefused(
            f"writing case {case.case_id} failed: {detail}", CASE_INVALID
        ) from None


def _write_member(path: Path, data: bytes) -> None:
    """Write `data` to `path`, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _record_members(record: Path) -> dict[str, bytes]:
    """The record's member bytes: the required lanes plus the optional nonclaims."""
    members: dict[str, bytes] = {}
    for key in REQUIRED_MEMBER_KEYS:
        try:
            members[key] = (record / f"{key}.json").read_bytes()
        except OSError:
            raise CorpusRefused(
                f"record {record} is missing {key}.json", CASE_INVALID
            ) from None
    nonclaims = record / "nonclaims.json"
    if nonclaims.is_file():
        members["nonclaims"] = nonclaims.read_bytes()
    return members


def _record_objects(record: Path) -> dict[str, bytes]:
    """The record's objects keyed by content hash; duplicate bytes collapse."""
    store = record / "objects"
    if not store.is_dir():
        raise CorpusRefused(
            f"record {record} is missing its objects/ directory", CASE_INVALID
        )
    objects: dict[str, bytes] = {}
    for path in sorted(store.iterdir()):
        if path.is_file():
            data = path.read_bytes()
            objects[hash_bytes(data)] = data
    return objects


def _record_paper(record: Path) -> tuple[str, bytes] | None:
    """The record's paper as (name, bytes), pdf preferred, else markdown; None if absent."""
    for name in _PAPER_FILES:
        path = record / name
        if path.is_file():
            return name, path.read_bytes()
    return None


def _derive_case(
    members: dict[str, bytes], objects: dict[str, bytes], paper: tuple[str, bytes] | None
) -> Case:
    """The fresh case: every identity field derived from the record's own bytes."""
    try:
        run_id = parse_trace(members["trace"]).run_id
    except ValueError as exc:
        raise CorpusRefused(f"record trace.json does not parse: {exc}", CASE_INVALID) from None
    member_hashes = {key: hash_bytes(data) for key, data in members.items()}
    tree = objects_tree_hash(objects)
    paper_hash = None if paper is None else hash_bytes(paper[1])
    return Case(
        format=FORMAT,
        case_id=derive_case_id(paper_hash, run_id, member_hashes, tree),
        paper_hash=paper_hash,
        run_id=run_id,
        member_hashes=member_hashes,
        objects_tree_hash=tree,
        has_labels=False,
    )


def _case_objects(case_dir: Path, case: Case) -> dict[str, bytes]:
    """The case's objects, each verified hash-named and matching the manifest tree."""
    store = case_dir / "objects"
    try:
        names = sorted(p.name for p in store.iterdir() if p.is_file())
    except OSError:
        raise CorpusRefused(
            f"case {case.case_id} is missing its objects/ directory", CASE_INVALID
        ) from None
    objects: dict[str, bytes] = {}
    for name in names:
        data = (store / name).read_bytes()
        if hash_bytes(data) != name:
            raise CorpusRefused(
                f"case {case.case_id} object {name} does not match its hash",
                CASE_TAMPERED,
            )
        objects[name] = data
    if objects_tree_hash(objects) != case.objects_tree_hash:
        raise CorpusRefused(
            f"case {case.case_id} objects do not match its manifest tree", CASE_TAMPERED
        )
    return objects


def _case_paper(case_dir: Path, case: Case) -> bytes | None:
    """The case's paper bytes, verified; a paper a manifest does not hash is refused."""
    if case.paper_hash is None:
        if any((case_dir / name).exists() for name in _PAPER_FILES):
            raise CorpusRefused(
                f"case {case.case_id} carries a paper its manifest does not hash",
                CASE_INVALID,
            )
        return None
    path = next(
        (case_dir / name for name in _PAPER_FILES if (case_dir / name).is_file()), None
    )
    if path is None:
        raise CorpusRefused(f"case {case.case_id} is missing its paper", CASE_INVALID)
    data = path.read_bytes()
    if hash_bytes(data) != case.paper_hash:
        raise CorpusRefused(
            f"case {case.case_id} paper does not match its manifest hash", CASE_TAMPERED
        )
    return data