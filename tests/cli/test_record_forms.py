"""Dual-form record read: `read_record` accepts the curated and the C1 claim forms.

Phase 1 of `docs/planning/cross-paper-coverage/bank-flag/plan_20261002.md`,
written failing first: `read_record` (`src/plumb/cli/replay.py:96-124`) reads
only the curated six-field claims document, and a C1-form record — the bytes
`serialize_claims` writes, `{"claims", "paper_hash"}` — must replay too, with
its paper hash checked against the record's own paper before anything is
re-admitted. Anything else is `ValueError` → `RECORD_INVALID`, never a replay;
the curated path stays byte-for-byte what it was (pinned by `test_replay.py`
and the gate suite).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from plumb.cli import RECORD_INVALID, main
from plumb.cli.replay import cross_check, read_record
from plumb.verify import Completed, load_bindings, verify_claims

_THIS_DIR = Path(__file__).parent
sys.path.insert(0, str(_THIS_DIR.parent / "corpus"))
from record_helpers import record_dir  # noqa: E402

_JSON = {"sort_keys": True, "ensure_ascii": False, "separators": (",", ":"), "allow_nan": False}


def _rewrite_json(path: Path, document: object) -> None:
    """Overwrite `path` with `document` in the house canonical JSON bytes."""
    path.write_bytes((json.dumps(document, **_JSON) + "\n").encode("utf-8"))


class TestAC1FormRecordReplays:
    """Acceptance 1: the C1 record replays through the whole read chain."""

    def test_read_record_and_the_c4_chain_succeed(self, tmp_path: Path) -> None:
        record = record_dir(tmp_path, form="c1")
        claims, bindings_bytes, trace, capture, _paper, paper_format = read_record(record)
        assert paper_format == "markdown"
        assert len(claims) == 1
        bindings = load_bindings(bindings_bytes, [c.id for c in claims])
        verdicts = verify_claims(claims, bindings, Completed(trace, capture))
        cross_check(record, verdicts)
        assert verdicts.verdicts[0].verdict == "REPRODUCED"

    def test_the_cli_json_stdout_is_byte_identical_to_the_record(
        self, tmp_path: Path, capsys
    ) -> None:
        record = record_dir(tmp_path, form="c1")
        code = main(["verify", "--from-record", str(record), "--json"])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out.encode("utf-8") == (record / "verdicts.json").read_bytes()


class TestAC1PaperHashMismatchIsRefused:
    """Acceptance 2: a tampered digest is `ValueError`, never a replay."""

    def test_a_tampered_digest_is_refused_by_read_record_and_the_cli(
        self, tmp_path: Path, capsys
    ) -> None:
        record = record_dir(tmp_path, form="c1")
        document = json.loads((record / "claims.json").read_bytes())
        digest = document["paper_hash"]["digest"]
        document["paper_hash"]["digest"] = ("0" if digest[0] != "0" else "1") + digest[1:]
        _rewrite_json(record / "claims.json", document)
        with pytest.raises(ValueError, match="paper_hash"):
            read_record(record)
        code = main(["verify", "--from-record", str(record), "--json"])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {RECORD_INVALID}: ")
        assert "Traceback" not in captured.err


class TestAnyOtherClaimDocumentShapeIsRefused:
    """Acceptance 3: a document with any other key set, or not an object."""

    def test_an_extra_field_key_set_is_refused(self, tmp_path: Path) -> None:
        record = record_dir(tmp_path, form="c1")
        document = json.loads((record / "claims.json").read_bytes())
        document["extra"] = True
        _rewrite_json(record / "claims.json", document)
        with pytest.raises(ValueError, match="not a claim document"):
            read_record(record)

    def test_a_non_object_document_is_refused(self, tmp_path: Path) -> None:
        record = record_dir(tmp_path, form="c1")
        (record / "claims.json").write_bytes(b'["claims"]\n')
        with pytest.raises(ValueError, match="not a claim document"):
            read_record(record)


class TestAC1RecordWhosePaperChangedIsRefused:
    """Acceptance 4: a paper that no longer matches the record is `ValueError`."""

    def test_a_changed_paper_is_refused(self, tmp_path: Path) -> None:
        record = record_dir(tmp_path, form="c1")
        (record / "paper.md").write_bytes(b"# Synthetic paper\n\nAUC was 0.88.\n")
        with pytest.raises(ValueError, match="paper_hash"):
            read_record(record)

class TestAWrongTypedCuratedEntryIsRefused:
    """Review fix: wrong-typed fields in a curated entry are `ValueError`
    (`RECORD_INVALID`), never a `TypeError` that surfaces as `SPINE_ERROR`."""

    def test_a_string_span_is_refused_by_read_record(self, tmp_path: Path) -> None:
        record = record_dir(tmp_path)
        document = json.loads((record / "claims.json").read_bytes())
        document["claims"][0]["start"] = "5"
        _rewrite_json(record / "claims.json", document)
        with pytest.raises(ValueError, match="wrong-typed field"):
            read_record(record)

    def test_a_string_span_is_record_invalid_through_the_cli(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        record = record_dir(tmp_path)
        document = json.loads((record / "claims.json").read_bytes())
        document["claims"][0]["start"] = "5"
        _rewrite_json(record / "claims.json", document)
        code = main(["verify", "--from-record", str(record), "--json"])
        captured = capsys.readouterr()
        assert code == 1
        assert captured.err.startswith(f"plumb verify: {RECORD_INVALID}: ")
        assert "Traceback" not in captured.err
