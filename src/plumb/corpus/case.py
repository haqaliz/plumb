"""The case record: content-addressed identity and canonical manifest bytes (Phase 1).

One banked verify run is a `Case` — the manifest of its member bytes (`claims`,
`bindings`, `trace`, `verdicts`, optional `nonclaims`) and their objects. The
manifest is the contract the bank and benchmark aspects read, so its key set is
explicit and its bytes are canonical: sorted keys, no incidental whitespace,
UTF-8 without escapes, no NaN, one trailing newline, and nothing from the
user's machine — no timestamp, no absolute path.

**Identity is content-addressed.** `case_id` is SHA-256 over the pinned list
`[format, paper_hash (or null), run_id, sorted member hashes, objects-tree
hash]`, `derive_run_id` style — the same members always derive the same id.
Labels are human annotations and never enter the identity; `has_labels` only
marks their presence. A record without a paper hashes `null`, never `""`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

__all__ = [
    "FORMAT",
    "MEMBER_KEYS",
    "REQUIRED_MEMBER_KEYS",
    "Case",
    "derive_case_id",
    "hash_bytes",
    "objects_tree_hash",
    "parse_case",
    "serialize_case",
]

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}

_HEX64 = re.compile(r"[0-9a-f]{64}")

#: The case format this manifest speaks; a manifest of any other format is refused.
FORMAT = "plumb-corpus-case/1"

#: The member lanes a case may carry, in pinned order; only present members are hashed.
MEMBER_KEYS = ("claims", "bindings", "trace", "verdicts", "nonclaims")

#: Every case must carry these members; `nonclaims` is the optional lane.
REQUIRED_MEMBER_KEYS = ("claims", "bindings", "trace", "verdicts")


@dataclass(frozen=True)
class Case:
    """One banked verify run: the manifest record of its members."""

    format: str
    case_id: str
    paper_hash: str | None
    run_id: str
    member_hashes: dict[str, str]
    objects_tree_hash: str
    has_labels: bool


def hash_bytes(data: bytes) -> str:
    """The SHA-256 of `data` as lowercase hex — the member-hash primitive."""
    return hashlib.sha256(data).hexdigest()


def objects_tree_hash(object_hashes: Iterable[str]) -> str:
    """SHA-256 over the canonical JSON of the sorted, deduplicated object hashes."""
    return hashlib.sha256(
        json.dumps(sorted(set(object_hashes)), **_JSON).encode("utf-8")
    ).hexdigest()


def derive_case_id(
    paper_hash: str | None,
    run_id: str,
    member_hashes: dict[str, str],
    objects_tree_hash: str,
) -> str:
    """SHA-256 over the pinned identity list: format, paper hash, run id,
    sorted member hashes, objects-tree hash. Labels are not inputs."""
    parts = [
        FORMAT,
        _hex64_or_none(paper_hash, "paper_hash"),
        _str(run_id, "run_id"),
        _checked_members(member_hashes),
        _hex64(objects_tree_hash, "objects_tree_hash"),
    ]
    return hashlib.sha256(json.dumps(parts, **_JSON).encode("utf-8")).hexdigest()


def serialize_case(case: Case) -> bytes:
    """The manifest as one canonical JSON line, UTF-8, newline-terminated."""
    return (json.dumps(_document(case), default=_refuse, **_JSON) + "\n").encode("utf-8")


def _document(case: Case) -> dict[str, Any]:
    return {
        "format": _str(case.format, "format"),
        "case_id": _str(case.case_id, "case_id"),
        "paper_hash": _hex64_or_none(case.paper_hash, "paper_hash"),
        "run_id": _str(case.run_id, "run_id"),
        "member_hashes": _checked_members(case.member_hashes),
        "objects_tree_hash": _hex64(case.objects_tree_hash, "objects_tree_hash"),
        "has_labels": _bool(case.has_labels, "has_labels"),
    }


def parse_case(data: bytes) -> Case:
    """The `Case` that `serialize_case` wrote as `data`; anything else is refused."""
    try:
        doc = json.loads(data.decode("utf-8"))
        case = Case(
            format=_typed(doc["format"], str),
            case_id=_typed(doc["case_id"], str),
            paper_hash=_hex64_or_none(doc["paper_hash"], "paper_hash"),
            run_id=_typed(doc["run_id"], str),
            member_hashes=_checked_members(doc["member_hashes"]),
            objects_tree_hash=_hex64(doc["objects_tree_hash"], "objects_tree_hash"),
            has_labels=_typed(doc["has_labels"], bool),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"not a serialized Case: {exc!r}") from None
    if case.format != FORMAT:
        raise ValueError(f"unsupported case format: {case.format!r}")
    if (
        derive_case_id(case.paper_hash, case.run_id, case.member_hashes, case.objects_tree_hash)
        != case.case_id
    ):
        raise ValueError("case_id does not match the manifest's members")
    return case


def _checked_members(member_hashes: object) -> dict[str, str]:
    if not isinstance(member_hashes, dict):
        raise TypeError(f"member_hashes must be a dict of str hashes, got {type(member_hashes).__name__}")
    extra = sorted(set(member_hashes) - set(MEMBER_KEYS))
    if extra:
        raise ValueError(f"unknown member key(s): {extra}")
    missing = sorted(set(REQUIRED_MEMBER_KEYS) - set(member_hashes))
    if missing:
        raise ValueError(f"missing member key(s): {missing}")
    return {key: _hex64(value, f"member hash {key}") for key, value in member_hashes.items()}


def _hex64_or_none(value: object, field: str) -> str | None:
    return None if value is None else _hex64(value, field)


def _hex64(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string, got {type(value).__name__}")
    if not _HEX64.fullmatch(value):
        raise ValueError(f"{field} must be a 64-char lowercase hex SHA-256, got {value!r}")
    return value


def _str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string, got {type(value).__name__}")
    return value


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field} must be a bool, got {type(value).__name__}")
    return value


def _typed(value: Any, kind: type) -> Any:
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise TypeError(f"expected {kind.__name__}, got {type(value).__name__}")
    return value


def _refuse(obj: object) -> Any:
    raise TypeError(f"no canonical encoding for {type(obj).__name__}: {obj!r}")