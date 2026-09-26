"""Build and verify a signed bundle (signed-bundle B3–B4, PRD B2–B5).

A bundle is a directory: a canonical `manifest.json` listing every other member by path,
SHA-256 and size; its SSHSIG `manifest.sig`; the claims, bindings, trace, verdicts and frozen
environment; and only the captured outputs the bindings read. `verify_bundle` checks, in
order, the signature (nothing unsigned is trusted before it), the members, refused content,
the structure, the claims' grounding in the paper, and the re-derived verdicts — reporting
named causes, never raising on content.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from plumb.bundle import (
    BUNDLE_CAUSES,
    BundleRefused,
    build_bundle,
    verify_bundle,
)
from plumb.bundle import causes as C
from plumb.bundle.sshsig import SshSigner
from plumb.verify import DIVERGED, REPRODUCED
from bundle_helpers import CLAIMS, PAPER, SOURCE, bindings_bytes, real_run

ENV = "python==3.12.13\nnumpy==2.5.3\n"


@pytest.fixture
def built(tmp_path: Path, signing_key):
    _, trace, capture = real_run(tmp_path)
    out = tmp_path / "bundle"
    build_bundle(
        out, claims=CLAIMS, paper=PAPER.encode(), paper_format="markdown",
        paper_source="https://example.org/paper", include_paper=True,
        bindings=bindings_bytes(), trace=trace, capture=capture, environment=ENV,
        source=SOURCE, signer=SshSigner(signing_key[0], "plumb-test"),
    )
    return out


def verify(bundle: Path, signing_key, **kw):
    return verify_bundle(bundle, allowed_signers=signing_key[1], principal="plumb-test", **kw)


def causes_of(report) -> set[str]:
    return {cause for cause, _ in report.causes}


class TestBuild:
    def test_the_members(self, built: Path) -> None:
        names = sorted(p.relative_to(built).as_posix() for p in built.rglob("*") if p.is_file())
        objects = [n for n in names if n.startswith("objects/")]
        assert set(names) - set(objects) == {
            "manifest.json", "manifest.sig", "claims.json", "bindings.json", "trace.json",
            "verdicts.json", "environment.txt", "paper.md",
        }
        assert len(objects) == 2  # results.json and stdout — the bound outputs only

    def test_stderr_is_never_a_member(self, built: Path) -> None:
        for path in (built / "objects").iterdir():
            assert b"secret" not in path.read_bytes()

    def test_the_manifest(self, built: Path) -> None:
        manifest = json.loads((built / "manifest.json").read_bytes())
        assert manifest["format"] == "plumb-bundle/1"
        assert manifest["signer"] == "plumb-test"
        assert manifest["source"]["rev_resolved"] == "0" * 40
        assert manifest["paper"]["format"] == "markdown" and manifest["paper"]["included"]
        paths = [m["path"] for m in manifest["members"]]
        assert paths == sorted(paths) and "manifest.sig" not in paths

    def test_the_verdicts_are_the_real_ones(self, built: Path) -> None:
        verdicts = json.loads((built / "verdicts.json").read_bytes())["verdicts"]
        assert sorted(v["verdict"] for v in verdicts) == [DIVERGED, REPRODUCED, REPRODUCED]

    def test_a_non_empty_target_is_refused(self, tmp_path: Path, signing_key) -> None:
        _, trace, capture = real_run(tmp_path)
        (tmp_path / "taken").mkdir()
        (tmp_path / "taken" / "x").write_text("x")
        with pytest.raises(BundleRefused):
            build_bundle(tmp_path / "taken", claims=CLAIMS, paper=PAPER.encode(),
                         paper_format="markdown", paper_source=None, include_paper=True,
                         bindings=bindings_bytes(), trace=trace, capture=capture,
                         environment=ENV, source=SOURCE,
                         signer=SshSigner(signing_key[0], "plumb-test"))

    def test_a_claim_the_paper_does_not_ground_is_refused_before_signing(
        self, tmp_path: Path, signing_key
    ) -> None:
        _, trace, capture = real_run(tmp_path)
        with pytest.raises(BundleRefused) as refused:
            build_bundle(tmp_path / "b", claims=CLAIMS, paper=b"# A different paper\n",
                         paper_format="markdown", paper_source=None, include_paper=True,
                         bindings=bindings_bytes(), trace=trace, capture=capture,
                         environment=ENV, source=SOURCE,
                         signer=SshSigner(signing_key[0], "plumb-test"))
        assert refused.value.cause == C.CLAIMS_UNGROUNDED
        assert not (tmp_path / "b" / "manifest.sig").exists()

    def test_a_local_path_in_a_member_is_refused_before_signing(
        self, tmp_path: Path, signing_key
    ) -> None:
        _, trace, capture = real_run(tmp_path)
        with pytest.raises(BundleRefused) as refused:
            build_bundle(tmp_path / "b", claims=CLAIMS, paper=PAPER.encode(),
                         paper_format="markdown", paper_source=None, include_paper=True,
                         bindings=bindings_bytes(), trace=trace, capture=capture,
                         environment=ENV + "# built in /Users/someone/work\n", source=SOURCE,
                         signer=SshSigner(signing_key[0], "plumb-test"))
        assert refused.value.cause == C.MEMBER_REFUSED

    def test_the_bundle_is_byte_identical_across_processes(
        self, built: Path, tmp_path: Path, signing_key
    ) -> None:
        child = (
            "import sys; from pathlib import Path\n"
            "from plumb.bundle import rebuild_bundle\n"
            "from plumb.bundle.sshsig import SshSigner\n"
            "rebuild_bundle(Path(sys.argv[1]), Path(sys.argv[2]),"
            " signer=SshSigner(sys.argv[3], 'plumb-test'))\n"
        )
        again = tmp_path / "again"
        env = {**os.environ, "PYTHONHASHSEED": "7"}
        subprocess.run([sys.executable, "-c", child, str(built), str(again), str(signing_key[0])],
                       check=True, env=env, capture_output=True, timeout=120)
        files = lambda root: {p.relative_to(root).as_posix(): p.read_bytes()
                              for p in root.rglob("*") if p.is_file()}
        assert files(again) == files(built)


class TestVerify:
    def test_a_good_bundle_verifies_and_re_derives(self, built: Path, signing_key) -> None:
        report = verify(built, signing_key)
        assert report.ok and report.causes == ()
        assert len(report.verdicts.verdicts) == 3

    def test_the_paper_can_be_supplied_by_the_verifier(
        self, tmp_path: Path, signing_key
    ) -> None:
        _, trace, capture = real_run(tmp_path)
        out = tmp_path / "b"
        build_bundle(out, claims=CLAIMS, paper=PAPER.encode(), paper_format="markdown",
                     paper_source=None, include_paper=False, bindings=bindings_bytes(),
                     trace=trace, capture=capture, environment=ENV, source=SOURCE,
                     signer=SshSigner(signing_key[0], "plumb-test"))
        assert not (out / "paper.md").exists()
        assert causes_of(verify(out, signing_key)) == {C.PAPER_MISSING}
        assert verify(out, signing_key, paper=PAPER.encode()).ok
        assert causes_of(verify(out, signing_key, paper=b"# other\n")) == {C.PAPER_MISMATCH}

    def test_a_missing_signature(self, built: Path, signing_key) -> None:
        (built / "manifest.sig").unlink()
        assert causes_of(verify(built, signing_key)) == {C.SIGNATURE_MISSING}

    def test_another_signer_is_not_trusted(self, built: Path, signing_key, other_key) -> None:
        report = verify_bundle(built, allowed_signers=other_key[1], principal="plumb-test")
        assert causes_of(report) == {C.SIGNATURE_INVALID} and report.verdicts is None

    def test_a_tampered_manifest_fails_the_signature(self, built: Path, signing_key) -> None:
        manifest = built / "manifest.json"
        manifest.write_bytes(manifest.read_bytes().replace(b"plumb-test", b"plumb-tesT"))
        assert causes_of(verify(built, signing_key)) == {C.SIGNATURE_INVALID}

    @pytest.mark.parametrize(
        "member",
        ["claims.json", "bindings.json", "trace.json", "verdicts.json", "environment.txt",
         "paper.md", "objects"],
    )
    def test_a_flipped_byte_in_any_member(self, built: Path, signing_key, member: str) -> None:
        path = next((built / "objects").iterdir()) if member == "objects" else built / member
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0x01
        path.write_bytes(bytes(data))
        assert causes_of(verify(built, signing_key)) == {C.MEMBER_TAMPERED}

    def test_a_missing_member(self, built: Path, signing_key) -> None:
        (built / "trace.json").unlink()
        assert causes_of(verify(built, signing_key)) == {C.MEMBER_MISSING}

    def test_an_unlisted_file(self, built: Path, signing_key) -> None:
        (built / "objects" / ("f" * 64)).write_bytes(b"extra")
        assert causes_of(verify(built, signing_key)) == {C.MEMBER_UNLISTED}

    def test_a_resigned_bundle_with_forged_verdicts(self, built: Path, signing_key) -> None:
        from plumb.bundle.build import resign

        verdicts = built / "verdicts.json"
        verdicts.write_bytes(verdicts.read_bytes().replace(b'"DIVERGED"', b'"REPRODUCED"'))
        resign(built, SshSigner(signing_key[0], "plumb-test"))
        assert causes_of(verify(built, signing_key)) == {C.VERDICTS_MISMATCH}

    def test_a_resigned_bundle_with_a_local_path(self, built: Path, signing_key) -> None:
        from plumb.bundle.build import resign

        env = built / "environment.txt"
        env.write_bytes(env.read_bytes() + b"# /home/someone\n")
        resign(built, SshSigner(signing_key[0], "plumb-test"))
        assert causes_of(verify(built, signing_key)) == {C.MEMBER_REFUSED}

    def test_a_resigned_bundle_with_a_stderr_object(self, built: Path, signing_key) -> None:
        from plumb.bundle.build import add_member_and_resign
        from plumb.run import parse_trace

        trace = parse_trace((built / "trace.json").read_bytes())
        stderr = next(a for a in trace.artifacts if a.diagnostic_only)
        add_member_and_resign(built, f"objects/{stderr.sha256}", b"anything",
                              SshSigner(signing_key[0], "plumb-test"))
        assert C.MEMBER_REFUSED in causes_of(verify(built, signing_key))

    def test_content_problems_never_raise(self, built: Path, signing_key) -> None:
        from plumb.bundle.build import resign

        (built / "trace.json").write_bytes(b"not json")
        resign(built, SshSigner(signing_key[0], "plumb-test"))
        assert causes_of(verify(built, signing_key)) == {C.MANIFEST_INVALID}

    def test_a_directory_that_is_not_a_bundle(self, tmp_path: Path, signing_key) -> None:
        assert causes_of(verify(tmp_path, signing_key)) == {C.MANIFEST_INVALID}


def test_the_cause_vocabulary() -> None:
    assert BUNDLE_CAUSES == {
        C.SIGNATURE_MISSING, C.SIGNATURE_INVALID, C.MANIFEST_INVALID, C.MEMBER_MISSING,
        C.MEMBER_TAMPERED, C.MEMBER_UNLISTED, C.MEMBER_REFUSED, C.PAPER_MISSING,
        C.PAPER_MISMATCH, C.CLAIMS_UNGROUNDED, C.VERDICTS_MISMATCH,
    }
