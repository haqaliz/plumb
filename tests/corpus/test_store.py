"""The corpus store: write-once banking and hash-verified reading (Phase 2).

Acceptance criteria 2-5 and 7 of `docs/planning/discrepancy-corpus/store/spec.md`,
written failing first against the Phase 1 manifest contract:

2. Round-trip: `bank_case` -> `read_case` -> every member byte-for-byte identical.
3. Re-bank of an identical record is a no-op: same case_id, case bytes unchanged.
4. Same case_id with different stored bytes -> refused (`CASE_CONFLICT`),
   existing case untouched — mutation-checked, the
   `test_false_diverged_guard.py` pattern (the refusal is pinned: remove it
   and the test fails).
5. A tampered stored member -> `read_case` refuses with `CASE_TAMPERED`, never
   returns forged bytes.
7. Duplicate object bytes collapse in `objects/`, labels never enter the
   identity, a failed new-case write is cleaned up, a malformed record is
   `CASE_INVALID`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

import plumb.corpus.store as store_module
from plumb.corpus import (
    CAUSES,
    CASE_CONFLICT,
    CASE_INVALID,
    CASE_TAMPERED,
    CorpusRefused,
    bank_case,
    derive_case_id,
    read_case,
)
from plumb.corpus.case import serialize_case
from record_helpers import nonclaims_json, record_dir

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under `root`, as a posix-relative path -> bytes snapshot."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _tamper_trace(case_dir: Path) -> None:
    """Rewrite the stored trace with different bytes the same run would carry.

    `started_at_ns` is provenance, not identity (`run/trace.py`), so the
    tampered trace parses to the same `run_id` — the case_id cannot change,
    only the member bytes.
    """
    path = case_dir / "trace.json"
    document = json.loads(path.read_bytes())
    document["started_at_ns"] += 1
    path.write_bytes((json.dumps(document, **_JSON) + "\n").encode("utf-8"))


# -----------------------------------------------------------------------------
# Round-trip (AC2)
# -----------------------------------------------------------------------------


def test_round_trip_is_byte_identical(tmp_path: Path) -> None:
    record = record_dir(tmp_path)
    case = bank_case(record, tmp_path / "store")
    case_dir = tmp_path / "store" / case.case_id
    got = read_case(case_dir)
    assert got.case == case
    assert got.paper == (record / "paper.md").read_bytes()
    for key, data in got.members.items():
        assert data == (record / f"{key}.json").read_bytes()
        assert (case_dir / f"{key}.json").read_bytes() == data
    expected = {
        hashlib.sha256(p.read_bytes()).hexdigest(): p.read_bytes()
        for p in (record / "objects").iterdir()
    }
    assert got.objects == expected
    assert (case_dir / "case.json").read_bytes() == serialize_case(case)


def test_round_trip_without_a_paper_file(tmp_path: Path) -> None:
    record = record_dir(tmp_path, paper=None)
    case = bank_case(record, tmp_path / "store")
    assert case.paper_hash is None
    got = read_case(tmp_path / "store" / case.case_id)
    assert got.paper is None
    assert got.case == case


def test_round_trip_carries_the_nonclaims_lane(tmp_path: Path) -> None:
    record = record_dir(tmp_path, nonclaims=nonclaims_json())
    case = bank_case(record, tmp_path / "store")
    assert set(case.member_hashes) == {"bindings", "claims", "nonclaims", "trace", "verdicts"}
    got = read_case(tmp_path / "store" / case.case_id)
    assert got.members["nonclaims"] == nonclaims_json()


# -----------------------------------------------------------------------------
# No-op re-bank (AC3)
# -----------------------------------------------------------------------------


def test_rebanking_the_identical_record_is_a_noop(tmp_path: Path) -> None:
    record = record_dir(tmp_path)
    store = tmp_path / "store"
    first = bank_case(record, store)
    snapshot = _tree_bytes(store)
    again = bank_case(record, store)
    assert again == first
    assert again.case_id == first.case_id
    assert _tree_bytes(store) == snapshot


# -----------------------------------------------------------------------------
# Conflict refusal (AC4), mutation-checked
# -----------------------------------------------------------------------------


def assert_conflict_refused(tmp_path: Path) -> str:
    record = record_dir(tmp_path)
    store = tmp_path / "store"
    case = bank_case(record, store)
    _tamper_trace(store / case.case_id)
    snapshot = _tree_bytes(store)
    cause = None
    try:
        bank_case(record, store)
    except CorpusRefused as exc:
        cause = exc.cause
    assert cause == CASE_CONFLICT, "the conflicting re-bank was not refused"
    assert _tree_bytes(store) == snapshot, "the existing case was touched"
    return cause


def test_a_rebank_with_different_stored_bytes_is_refused(tmp_path: Path) -> None:
    assert assert_conflict_refused(tmp_path) == CASE_CONFLICT


class TestMutations:
    def test_removing_the_conflict_refusal_breaks_the_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(store_module, "_reject_conflict", lambda case_dir, fresh: None)
        with pytest.raises(AssertionError, match="not refused"):
            assert_conflict_refused(tmp_path)


# -----------------------------------------------------------------------------
# Tampered stored member (AC5)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("member", ["claims", "bindings", "trace", "verdicts"])
def test_a_tampered_stored_member_is_refused_on_read(
    tmp_path: Path, member: str
) -> None:
    case = bank_case(record_dir(tmp_path), tmp_path / "store")
    (tmp_path / "store" / case.case_id / f"{member}.json").write_bytes(b"forged bytes")
    with pytest.raises(CorpusRefused) as exc:
        read_case(tmp_path / "store" / case.case_id)
    assert exc.value.cause == CASE_TAMPERED


def test_a_tampered_stored_object_is_refused_on_read(tmp_path: Path) -> None:
    case = bank_case(record_dir(tmp_path), tmp_path / "store")
    objects_dir = tmp_path / "store" / case.case_id / "objects"
    victim = next(objects_dir.iterdir())
    victim.write_bytes(b"forged bytes")
    with pytest.raises(CorpusRefused) as exc:
        read_case(tmp_path / "store" / case.case_id)
    assert exc.value.cause == CASE_TAMPERED


def test_a_tampered_stored_paper_is_refused_on_read(tmp_path: Path) -> None:
    case = bank_case(record_dir(tmp_path), tmp_path / "store")
    (tmp_path / "store" / case.case_id / "paper.md").write_bytes(b"forged paper")
    with pytest.raises(CorpusRefused) as exc:
        read_case(tmp_path / "store" / case.case_id)
    assert exc.value.cause == CASE_TAMPERED


def test_a_missing_stored_member_is_invalid_on_read(tmp_path: Path) -> None:
    case = bank_case(record_dir(tmp_path), tmp_path / "store")
    (tmp_path / "store" / case.case_id / "verdicts.json").unlink()
    with pytest.raises(CorpusRefused) as exc:
        read_case(tmp_path / "store" / case.case_id)
    assert exc.value.cause == CASE_INVALID


def test_a_missing_stored_manifest_is_invalid_on_read(tmp_path: Path) -> None:
    case = bank_case(record_dir(tmp_path), tmp_path / "store")
    (tmp_path / "store" / case.case_id / "case.json").unlink()
    with pytest.raises(CorpusRefused) as exc:
        read_case(tmp_path / "store" / case.case_id)
    assert exc.value.cause == CASE_INVALID


# -----------------------------------------------------------------------------
# Objects collapse (AC7)
# -----------------------------------------------------------------------------


def test_duplicate_object_bytes_collapse_in_the_store(tmp_path: Path) -> None:
    record = record_dir(tmp_path)
    duplicate = b"same bytes twice"
    (record / "objects" / "dup1").write_bytes(duplicate)
    (record / "objects" / "dup2").write_bytes(duplicate)
    case = bank_case(record, tmp_path / "store")
    distinct = {hashlib.sha256(p.read_bytes()).hexdigest() for p in (record / "objects").iterdir()}
    stored = {p.name: p.read_bytes() for p in (tmp_path / "store" / case.case_id / "objects").iterdir()}
    assert set(stored) == distinct
    assert len(stored) == len(distinct) < 4
    assert stored[hashlib.sha256(duplicate).hexdigest()] == duplicate


# -----------------------------------------------------------------------------
# Labels stay outside identity
# -----------------------------------------------------------------------------


def test_no_labels_banks_with_has_labels_false(tmp_path: Path) -> None:
    case = bank_case(record_dir(tmp_path), tmp_path / "store")
    assert case.has_labels is False
    assert case.labels_hash is None
    assert not (tmp_path / "store" / case.case_id / "labels.json").exists()
    document = json.loads((tmp_path / "store" / case.case_id / "case.json").read_bytes())
    assert document["has_labels"] is False
    assert document["labels_hash"] is None


def test_a_stray_labels_file_in_the_record_dir_is_inert(tmp_path: Path) -> None:
    record = record_dir(tmp_path)
    labeled = tmp_path / "labeled"
    shutil.copytree(record, labeled)
    (labeled / "labels.json").write_bytes(b'{"c1": "confirmed"}\n')
    plain = bank_case(record, tmp_path / "s1")
    with_labels = bank_case(labeled, tmp_path / "s2")
    assert plain.case_id == with_labels.case_id
    assert plain.has_labels is False and with_labels.has_labels is False
    assert not (tmp_path / "s2" / with_labels.case_id / "labels.json").exists()


# -----------------------------------------------------------------------------
# Label transport (Phase 1): canonical labels.json, manifest labels_hash
# -----------------------------------------------------------------------------


def test_labels_are_written_canonically_and_hashed(tmp_path: Path) -> None:
    record = record_dir(tmp_path)
    labels = {"z-claim": "confirmed", "a-claim": "refuted"}
    case = bank_case(record, tmp_path / "store", labels=labels)
    case_dir = tmp_path / "store" / case.case_id
    canonical = b'{"a-claim":"refuted","z-claim":"confirmed"}\n'
    assert (case_dir / "labels.json").read_bytes() == canonical
    assert case.has_labels is True
    assert case.labels_hash == hashlib.sha256(canonical).hexdigest()
    document = json.loads((case_dir / "case.json").read_bytes())
    assert document["has_labels"] is True
    assert document["labels_hash"] == case.labels_hash


def test_labels_never_enter_the_case_id(tmp_path: Path) -> None:
    record = record_dir(tmp_path)
    labels_a = {"c1": "confirmed"}
    labels_b = {"c1": "refuted"}
    case_a = bank_case(record, tmp_path / "s1", labels=labels_a)
    case_b = bank_case(record, tmp_path / "s2", labels=labels_b)
    assert case_a.case_id == case_b.case_id
    with pytest.raises(CorpusRefused) as exc:
        bank_case(record, tmp_path / "s1", labels=labels_b)
    assert exc.value.cause == CASE_CONFLICT
    assert read_case(tmp_path / "s1" / case_a.case_id).labels == labels_a


def test_rebanking_with_the_same_labels_is_a_noop(tmp_path: Path) -> None:
    record = record_dir(tmp_path)
    store = tmp_path / "store"
    labels = {"c1": "confirmed"}
    first = bank_case(record, store, labels=labels)
    snapshot = _tree_bytes(store)
    again = bank_case(record, store, labels=labels)
    assert again == first
    assert again.case_id == first.case_id
    assert _tree_bytes(store) == snapshot


def test_a_tampered_stored_labels_file_is_refused_on_read(tmp_path: Path) -> None:
    case = bank_case(record_dir(tmp_path), tmp_path / "store", labels={"c1": "confirmed"})
    (tmp_path / "store" / case.case_id / "labels.json").write_bytes(b'{"c1": "refuted"}\n')
    with pytest.raises(CorpusRefused) as exc:
        read_case(tmp_path / "store" / case.case_id)
    assert exc.value.cause == CASE_TAMPERED


def test_case_read_labels_round_trip(tmp_path: Path) -> None:
    labels = {"c1": "confirmed", "c2": "refuted"}
    case = bank_case(record_dir(tmp_path), tmp_path / "store", labels=labels)
    got = read_case(tmp_path / "store" / case.case_id)
    assert got.labels == labels
    plain = bank_case(record_dir(tmp_path / "plain"), tmp_path / "plain-store")
    assert read_case(tmp_path / "plain-store" / plain.case_id).labels is None


def _rewrite_manifest(case_dir: Path, document: object) -> None:
    (case_dir / "case.json").write_bytes(
        (json.dumps(document, **_JSON) + "\n").encode("utf-8")
    )


@pytest.mark.parametrize(
    "tweak",
    [
        lambda doc: {**doc, "has_labels": True, "labels_hash": None},
        lambda doc: {**doc, "has_labels": False},
    ],
)
def test_manifest_has_labels_labels_hash_disagreement_is_invalid(
    tmp_path: Path, tweak
) -> None:
    case = bank_case(record_dir(tmp_path), tmp_path / "store", labels={"c1": "confirmed"})
    case_dir = tmp_path / "store" / case.case_id
    document = json.loads((case_dir / "case.json").read_bytes())
    _rewrite_manifest(case_dir, tweak(document))
    with pytest.raises(CorpusRefused) as exc:
        read_case(case_dir)
    assert exc.value.cause == CASE_INVALID


# -----------------------------------------------------------------------------
# New-case write failure
# -----------------------------------------------------------------------------


def test_a_failed_new_case_write_cleans_up_and_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = record_dir(tmp_path)
    store = tmp_path / "store"
    real = store_module._write_member
    calls = 0

    def flaky(path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return real(path, data)

    monkeypatch.setattr(store_module, "_write_member", flaky)
    with pytest.raises(CorpusRefused) as exc:
        bank_case(record, store)
    assert exc.value.cause == CASE_INVALID
    assert not store.exists() or not any(store.iterdir())


def test_a_new_case_whose_write_fails_verification_is_cleaned_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = record_dir(tmp_path)
    store = tmp_path / "store"
    real = store_module._write_member

    def corrupt(path: Path, data: bytes) -> None:
        if path.name == "trace.json" and path.parent.name != "objects":
            data = b"corrupted on the way down"
        return real(path, data)

    monkeypatch.setattr(store_module, "_write_member", corrupt)
    with pytest.raises(CorpusRefused) as exc:
        bank_case(record, store)
    assert exc.value.cause == CASE_INVALID
    assert not store.exists() or not any(store.iterdir())


# -----------------------------------------------------------------------------
# Malformed record
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: (record / "bindings.json").unlink(),
        lambda record: (record / "trace.json").write_bytes(b"not a trace"),
        lambda record: shutil.rmtree(record / "objects"),
    ],
)
def test_a_malformed_record_is_refused(tmp_path: Path, mutate) -> None:
    record = record_dir(tmp_path)
    mutate(record)
    store = tmp_path / "store"
    with pytest.raises(CorpusRefused) as exc:
        bank_case(record, store)
    assert exc.value.cause == CASE_INVALID
    assert not store.exists() or not any(store.iterdir())


# -----------------------------------------------------------------------------
# The public seam
# -----------------------------------------------------------------------------


def test_the_public_seam() -> None:
    from plumb import corpus

    assert corpus.bank_case is bank_case
    assert corpus.read_case is read_case
    assert corpus.derive_case_id is derive_case_id
    assert corpus.CorpusRefused is CorpusRefused
    assert corpus.CAUSES == CAUSES
    assert corpus.CASE_CONFLICT == CASE_CONFLICT
    assert corpus.CASE_TAMPERED == CASE_TAMPERED
    assert corpus.CASE_INVALID == CASE_INVALID