"""Bundle packaging and rotation (issue #20).

A bundle is a directory; `pack` turns it into one deterministic archive, `unpack` brings it back
for verification. Extraction is a trust boundary — an archive is untrusted input — so absolute
paths, `..`, links and devices are refused before anything is written.
"""

from __future__ import annotations

import io
from pathlib import Path
import tarfile

import pytest

from plumb.bundle import BundleRefused, build_bundle, verify_bundle
from plumb.bundle import causes as C
from plumb.bundle.pack import is_archive, pack, unpack
from plumb.bundle.sshsig import SshSigner
from bundle_helpers import CLAIMS, PAPER, SOURCE, bindings_bytes, real_run

ENV = "python==3.12.13\n"


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


def members_of(archive: Path) -> list[tarfile.TarInfo]:
    with tarfile.open(archive) as tar:
        return tar.getmembers()


class TestPackaging:
    def test_pack_is_byte_deterministic(self, tmp_path: Path, built: Path) -> None:
        for suffix in (".tar", ".tar.gz"):
            first = pack(built, tmp_path / f"one{suffix}")
            second = pack(built, tmp_path / f"two{suffix}")
            assert first.read_bytes() == second.read_bytes()

    def test_entries_are_normalised(self, tmp_path: Path, built: Path) -> None:
        archive = pack(built, tmp_path / "b.tar")
        members = members_of(archive)
        names = [m.name for m in members]
        assert names == sorted(names)
        for member in members:
            assert member.mtime == 0
            assert (member.uid, member.gid) == (0, 0)
            assert (member.uname, member.gname) == ("", "")
            assert member.mode == 0o644
            assert member.isfile()

    def test_packed_bundle_unpacks_and_still_verifies(
        self, tmp_path: Path, built: Path, signing_key
    ) -> None:
        archive = pack(built, tmp_path / "b.tar.gz")
        restored = unpack(archive, tmp_path / "restored")
        report = verify_bundle(restored, allowed_signers=signing_key[1], principal="plumb-test")
        assert report.ok, report.causes
        assert sorted(p.relative_to(restored).as_posix() for p in restored.rglob("*") if p.is_file()) == sorted(
            p.relative_to(built).as_posix() for p in built.rglob("*") if p.is_file()
        )

    def test_is_archive(self, tmp_path: Path, built: Path) -> None:
        assert is_archive(pack(built, tmp_path / "b.tar"))
        assert is_archive(pack(built, tmp_path / "b.tar.gz"))
        assert not is_archive(built)
        assert not is_archive(tmp_path / "nope.tar")


def _tar(tmp_path: Path, name: str, entries) -> Path:
    path = tmp_path / name
    with tarfile.open(path, "w") as tar:
        for entry in entries:
            tar.addfile(*entry)
    return path


class TestUnsafeArchivesAreRefused:
    @pytest.mark.parametrize("name", ["../escape.txt", "/absolute.txt"])
    def test_a_path_outside_the_destination_is_refused(
        self, tmp_path: Path, name: str
    ) -> None:
        data = b"nope"
        info = tarfile.TarInfo(name)
        info.size = len(data)
        archive = _tar(tmp_path, "evil.tar", [(info, io.BytesIO(data))])
        with pytest.raises(BundleRefused) as refused:
            unpack(archive, tmp_path / "dest")
        assert refused.value.cause == C.MEMBER_REFUSED
        assert not (tmp_path / "escape.txt").exists()
        assert not Path("/absolute.txt").exists()

    def test_a_link_is_refused(self, tmp_path: Path) -> None:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "manifest.json"
        archive = _tar(tmp_path, "link.tar", [(info, None)])
        with pytest.raises(BundleRefused) as refused:
            unpack(archive, tmp_path / "dest")
        assert refused.value.cause == C.MEMBER_REFUSED

    def test_an_unreadable_archive_is_a_manifest_cause(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.tar"
        bad.write_bytes(b"not a tar")
        with pytest.raises(BundleRefused) as refused:
            unpack(bad, tmp_path / "dest")
        assert refused.value.cause == C.MANIFEST_INVALID


class TestCreatedTimestamp:
    def test_created_is_signed_when_supplied(self, tmp_path: Path, signing_key) -> None:
        _, trace, capture = real_run(tmp_path)
        out = tmp_path / "stamped"
        build_bundle(
            out, claims=CLAIMS, paper=PAPER.encode(), paper_format="markdown",
            paper_source="https://example.org/paper", include_paper=True,
            bindings=bindings_bytes(), trace=trace, capture=capture, environment=ENV,
            source=SOURCE, signer=SshSigner(signing_key[0], "plumb-test"),
            created="2026-10-21T00:00:00Z",
        )
        report = verify_bundle(out, allowed_signers=signing_key[1], principal="plumb-test")
        assert report.ok, report.causes
        assert report.manifest["created"] == "2026-10-21T00:00:00Z"

    def test_absent_by_default(self, built: Path) -> None:
        assert "created" not in (built / "manifest.json").read_text(encoding="utf-8")


class TestKeyRotation:
    def test_a_rotated_file_with_old_and_new_keys_verifies(
        self, tmp_path: Path, built: Path, signing_key, other_key
    ) -> None:
        rotated = tmp_path / "rotated_allowed_signers"
        retired = other_key[1].read_text(encoding="utf-8")
        current = signing_key[1].read_text(encoding="utf-8")
        rotated.write_text(retired + current, encoding="utf-8")
        assert verify_bundle(built, allowed_signers=rotated, principal="plumb-test").ok

    def test_a_file_holding_only_a_retired_key_refuses(
        self, built: Path, other_key
    ) -> None:
        report = verify_bundle(built, allowed_signers=other_key[1], principal="plumb-test")
        assert not report.ok
        assert {cause for cause, _ in report.causes} == {C.SIGNATURE_INVALID}
