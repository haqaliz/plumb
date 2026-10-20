"""`plumb bundle verify|inspect|pack` (issue #20).

The CLI is what a third party runs: no Python, no repo checkout. Verification is the same
`verify_bundle` the engine uses; `inspect` reads unauthenticated manifest fields and says so.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from plumb.cli import main

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "bundles" / "agrodesign"
ALLOWED = ROOT / "bundles" / "allowed_signers"


def bundle_argv(*extra: str) -> list[str]:
    return ["bundle", *extra]


class TestVerify:
    def test_the_committed_bundle_verifies(self, capsys) -> None:
        code = main(bundle_argv(
            "verify", str(BUNDLE), "--allowed-signers", str(ALLOWED),
        ))
        captured = capsys.readouterr()
        assert code == 0
        assert "bundle ok" in captured.out
        assert "86 claims" in captured.out
        assert captured.err == ""

    def test_the_json_document(self, capsys) -> None:
        code = main(bundle_argv(
            "verify", str(BUNDLE), "--allowed-signers", str(ALLOWED), "--json",
        ))
        document = json.loads(capsys.readouterr().out)
        assert code == 0
        assert document["ok"] is True
        assert document["signer"] == "plumb-bundle"
        assert document["claims"] == 86
        assert document["causes"] == []

    def test_a_wrong_principal_is_refused(self, capsys) -> None:
        code = main(bundle_argv(
            "verify", str(BUNDLE), "--allowed-signers", str(ALLOWED),
            "--principal", "someone-else",
        ))
        captured = capsys.readouterr()
        assert code == 1
        assert "SIGNATURE_INVALID" in captured.err
        assert "Traceback" not in captured.err

    def test_a_tampered_member_is_refused(self, tmp_path: Path, capsys) -> None:
        copy = tmp_path / "bundle"
        shutil.copytree(BUNDLE, copy)
        target = copy / "verdicts.json"
        target.write_bytes(target.read_bytes() + b" ")
        code = main(bundle_argv(
            "verify", str(copy), "--allowed-signers", str(ALLOWED),
        ))
        captured = capsys.readouterr()
        assert code == 1
        assert "MEMBER_TAMPERED" in captured.err

    def test_allowed_signers_is_required(self, capsys) -> None:
        assert main(bundle_argv("verify", str(BUNDLE))) == 2
        assert "--allowed-signers" in capsys.readouterr().err


class TestInspect:
    def test_it_names_the_fields_and_the_unchecked_signature(self, capsys) -> None:
        code = main(bundle_argv("inspect", str(BUNDLE)))
        out = capsys.readouterr().out
        assert code == 0
        assert "format: plumb-bundle/1" in out
        assert "signer: plumb-bundle" in out
        assert "signature: not checked" in out
        assert "created: none" in out

    def test_the_json_document(self, capsys) -> None:
        code = main(bundle_argv("inspect", str(BUNDLE), "--json"))
        document = json.loads(capsys.readouterr().out)
        assert code == 0
        assert document["signature_checked"] is False
        assert document["format"] == "plumb-bundle/1"
        assert document["members"] > 0


class TestPack:
    def test_pack_then_verify_the_archive(self, tmp_path: Path, capsys) -> None:
        archive = tmp_path / "agrodesign.tar.gz"
        assert main(bundle_argv("pack", str(BUNDLE), "--out", str(archive))) == 0
        assert archive.is_file()
        capsys.readouterr()

        code = main(bundle_argv(
            "verify", str(archive), "--allowed-signers", str(ALLOWED),
        ))
        captured = capsys.readouterr()
        assert code == 0
        assert "bundle ok" in captured.out

    def test_packing_a_non_bundle_is_a_named_cause(self, tmp_path: Path, capsys) -> None:
        empty = tmp_path / "not-a-bundle"
        empty.mkdir()
        code = main(bundle_argv("pack", str(empty), "--out", str(tmp_path / "x.tar")))
        captured = capsys.readouterr()
        assert code == 1
        assert "MANIFEST_INVALID" in captured.err
