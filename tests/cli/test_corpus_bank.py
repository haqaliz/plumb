"""corpus bank: `plumb corpus bank <record-dir> [--store DIR]` (bank Phase 2).

Acceptance criteria 1, 3, 4, 6 and 7 of `docs/planning/discrepancy-corpus/bank/spec.md`
on synthetic records, written failing first against the shell, in the in-process
`main([...])` pattern (`tests/cli/test_replay.py:146`):

1. A synthetic record banks under `--store`: exit 0, `banked <case_id>`, and the
   case's members are byte-identical to the record's (claims/bindings/trace/
   verdicts verbatim; `nonclaims.json` == the record's `unrepresentable.json`
   verbatim; objects match).
2. A re-bank is a no-op: exit 0, `already banked: <case_id>`, case bytes unchanged.
3. A record whose committed `verdicts.json` disagrees with re-derivation is
   `RECORD_INVALID`; nothing is banked.
4. Malformed labels (unknown claim id, invalid value, non-object, unparseable)
   are `RECORD_INVALID`; nothing is banked. A different label set on a re-bank
   is `CORPUS_REFUSED` (`CASE_CONFLICT`), the existing case untouched.
5. A valid record-side `labels.json` transports into the case byte-identically;
   the manifest carries `has_labels` true; no labels file -> no labels written.
6. A missing record dir is a usage error (exit 2); `plumb corpus` without a
   subcommand is a usage error.
7. `--store` is respected; no failure path ever prints a traceback.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

from plumb.cli import CORPUS_REFUSED, RECORD_INVALID, main
from plumb.corpus import read_case

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent / "corpus"))
from record_helpers import nonclaims_json, record_dir  # noqa: E402


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under `root`, as a posix-relative path -> bytes snapshot."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _claim_id(record: Path) -> str:
    """The single claim's id, from the record's own bindings lane.

    The curated claims lane carries no id — the admission gate derives it on
    re-admission — but the bindings were derived under it, and the re-admitted
    claim derives the same one (the id covers text, metric and units only).
    """
    document = json.loads((record / "bindings.json").read_bytes())
    return document["bindings"][0]["claim_id"]


class TestBankWritesACase:
    """Acceptance 1: exit 0, byte-identical members under `--store`."""

    def test_every_member_round_trips_byte_identically(
        self, tmp_path: Path, capsys
    ) -> None:
        record = record_dir(tmp_path, unrepresentable=nonclaims_json())
        store = tmp_path / "store"
        code = main(["corpus", "bank", str(record), "--store", str(store)])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        case_id = captured.out.strip().split()[1]
        assert captured.out == f"banked {case_id}\n"
        case_dir = store / case_id
        for name in ("claims.json", "bindings.json", "trace.json", "verdicts.json"):
            assert (case_dir / name).read_bytes() == (record / name).read_bytes()
        assert (case_dir / "nonclaims.json").read_bytes() == (
            record / "unrepresentable.json"
        ).read_bytes()
        assert (case_dir / "paper.md").read_bytes() == (record / "paper.md").read_bytes()
        expected = {p.name: p.read_bytes() for p in (record / "objects").iterdir()}
        got = {p.name: p.read_bytes() for p in (case_dir / "objects").iterdir()}
        assert got == expected
        got_case = read_case(case_dir)
        assert got_case.case.case_id == case_id
        assert got_case.members["nonclaims"] == nonclaims_json()


class TestRebankIsANoop:
    """Acceptance 2: exit 0, `already banked`, case bytes unchanged."""

    def test_rebank_prints_already_banked_and_touches_nothing(
        self, tmp_path: Path, capsys
    ) -> None:
        record = record_dir(tmp_path)
        store = tmp_path / "store"
        assert main(["corpus", "bank", str(record), "--store", str(store)]) == 0
        case_id = capsys.readouterr().out.strip().split()[1]
        snapshot = _tree_bytes(store)
        code = main(["corpus", "bank", str(record), "--store", str(store)])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.out == f"already banked: {case_id}\n"
        assert captured.err == ""
        assert _tree_bytes(store) == snapshot


class TestAConflictingVerdictsIsRefused:
    """Acceptance 3: committed vs re-derived disagreement is `RECORD_INVALID`."""

    def test_a_tampered_committed_verdicts_is_refused_and_banks_nothing(
        self, tmp_path: Path, capsys
    ) -> None:
        record = record_dir(tmp_path)
        path = record / "verdicts.json"
        data = bytearray(path.read_bytes())
        data[0] ^= 0x01
        path.write_bytes(bytes(data))
        store = tmp_path / "store"
        code = main(["corpus", "bank", str(record), "--store", str(store)])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {RECORD_INVALID}: ")
        assert "Traceback" not in captured.err
        assert not store.exists() or not any(store.iterdir())


class TestMalformedLabelsAreRecordInvalid:
    """Acceptance 4: malformed labels refuse the bank; nothing is banked."""

    def _bank(self, tmp_path: Path, capsys, record: Path) -> None:
        store = tmp_path / "store"
        code = main(["corpus", "bank", str(record), "--store", str(store)])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {RECORD_INVALID}: ")
        assert "Traceback" not in captured.err
        assert not store.exists() or not any(store.iterdir())

    def test_an_unknown_claim_id(self, tmp_path: Path, capsys) -> None:
        record = record_dir(tmp_path)
        (record / "labels.json").write_bytes(b'{"' + b"0" * 64 + b'": "confirmed"}\n')
        self._bank(tmp_path, capsys, record)

    def test_an_invalid_label_value(self, tmp_path: Path, capsys) -> None:
        record = record_dir(tmp_path)
        claim_id = _claim_id(record)
        (record / "labels.json").write_bytes(f'{{"{claim_id}": "bogus"}}\n'.encode())
        self._bank(tmp_path, capsys, record)

    def test_a_non_object_document(self, tmp_path: Path, capsys) -> None:
        record = record_dir(tmp_path)
        (record / "labels.json").write_bytes(b'["confirmed"]\n')
        self._bank(tmp_path, capsys, record)

    def test_unparseable_json(self, tmp_path: Path, capsys) -> None:
        record = record_dir(tmp_path)
        (record / "labels.json").write_bytes(b"not json\n")
        self._bank(tmp_path, capsys, record)


class TestAConflictingRebankIsCorpusRefused:
    """A different label set for the same record: `CORPUS_REFUSED`, case untouched."""

    def test_a_different_label_set_is_refused(self, tmp_path: Path, capsys) -> None:
        record = record_dir(tmp_path)
        claim_id = _claim_id(record)
        labels = f'{{"{claim_id}":"confirmed"}}\n'.encode()
        (record / "labels.json").write_bytes(labels)
        store = tmp_path / "store"
        assert main(["corpus", "bank", str(record), "--store", str(store)]) == 0
        case_id = capsys.readouterr().out.strip().split()[1]
        snapshot = _tree_bytes(store)
        (record / "labels.json").write_bytes(f'{{"{claim_id}":"refuted"}}\n'.encode())
        code = main(["corpus", "bank", str(record), "--store", str(store)])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {CORPUS_REFUSED}: ")
        assert "already exists with a different manifest" in captured.err
        assert "Traceback" not in captured.err
        assert _tree_bytes(store) == snapshot
        assert read_case(store / case_id).labels == {claim_id: "confirmed"}


class TestLabelsAreTransported:
    """Acceptance 5: record-side labels become the case's, byte-identically."""

    def test_valid_labels_transport_into_the_case(self, tmp_path: Path, capsys) -> None:
        record = record_dir(tmp_path)
        claim_id = _claim_id(record)
        labels_bytes = f'{{"{claim_id}":"confirmed"}}\n'.encode()
        (record / "labels.json").write_bytes(labels_bytes)
        store = tmp_path / "store"
        code = main(["corpus", "bank", str(record), "--store", str(store)])
        assert code == 0
        case_id = capsys.readouterr().out.strip().split()[1]
        case_dir = store / case_id
        assert (case_dir / "labels.json").read_bytes() == labels_bytes
        document = json.loads((case_dir / "case.json").read_bytes())
        assert document["has_labels"] is True
        assert document["labels_hash"] == hashlib.sha256(labels_bytes).hexdigest()

    def test_no_labels_file_banks_without_labels(self, tmp_path: Path, capsys) -> None:
        record = record_dir(tmp_path)
        store = tmp_path / "store"
        code = main(["corpus", "bank", str(record), "--store", str(store)])
        assert code == 0
        case_id = capsys.readouterr().out.strip().split()[1]
        case_dir = store / case_id
        assert not (case_dir / "labels.json").exists()
        document = json.loads((case_dir / "case.json").read_bytes())
        assert document["has_labels"] is False


class TestUsageErrorsExitTwo:
    """Acceptance 6: a missing record dir and a bare `corpus` are usage errors."""

    def test_a_missing_record_dir_is_a_usage_error(self, capsys) -> None:
        code = main(["corpus", "bank", "no-such-record", "--store", "tmp"])
        assert code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "no-such-record" in captured.err
        assert "Traceback" not in captured.err

    def test_corpus_without_a_subcommand_is_a_usage_error(self, capsys) -> None:
        code = main(["corpus"])
        assert code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Traceback" not in captured.err


class TestTheShellContract:
    """Acceptance 7: `--store` respected; never a traceback on any path."""

    def test_store_is_respected(self, tmp_path: Path, capsys, monkeypatch) -> None:
        record = record_dir(tmp_path)
        store = tmp_path / "elsewhere"
        monkeypatch.chdir(tmp_path)
        assert main(["corpus", "bank", str(record), "--store", str(store)]) == 0
        case_id = capsys.readouterr().out.strip().split()[1]
        assert (store / case_id).is_dir()
        assert not (tmp_path / "corpus" / "local").exists()

    def test_no_failure_path_prints_a_traceback(self, tmp_path: Path, capsys) -> None:
        record = record_dir(tmp_path)
        tampered = tmp_path / "tampered"
        shutil.copytree(record, tampered)
        path = tampered / "verdicts.json"
        data = bytearray(path.read_bytes())
        data[0] ^= 0x01
        path.write_bytes(bytes(data))
        cases = [
            ["corpus", "bank", str(tampered), "--store", str(tmp_path / "s1")],
            ["corpus", "bank", "no-such-record", "--store", str(tmp_path / "s2")],
            ["corpus"],
        ]
        for argv in cases:
            code = main(argv)
            assert isinstance(code, int)
            assert "Traceback" not in capsys.readouterr().err