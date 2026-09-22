"""Source resolution: local paths, git URLs, and archives → pinned checkouts (I2).

Every resolver returns a `Checkout(checkout_dir, tree_hash, source_record)`.
Git sources pin the repository's own tree object (`git-tree` scheme); local
dirs and archives use the deterministic plumb bytes framing (`plumb` scheme).
Failures resolve to named causes — `SourceNotFound`, `RevNotFound`,
`UnsupportedArchive` — never silent drops.

Everything here is offline: git resolution runs against local `file://` repos
synthesized in tmp dirs, and archives are built and read in-process. The only
subprocesses are local `git` calls.
"""

from __future__ import annotations

import io
from pathlib import Path
import subprocess
import tarfile
import zipfile

import pytest

from plumb.intake.causes import RevNotFound, SourceNotFound, UnsupportedArchive
from plumb.intake.checkout import _DEFAULT_SIZE_CAP_BYTES, resolve_archive, resolve_git, resolve_local
from plumb.intake.tree import git_tree_hash, plumb_tree_hash

GIT_ENV = ["-c", "user.name=Plumb Test", "-c", "user.email=test@plumb.local"]


def make_git_repo(root: Path, commits: list[tuple[str, dict[str, bytes]]]) -> Path:
    """Synthesize a local git repo; returns its path. Offline by construction."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, timeout=60)
    for message, files in commits:
        for rel, data in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, timeout=60)
        subprocess.run(
            ["git", *GIT_ENV, "commit", "-q", "-m", message],
            cwd=root,
            check=True,
            timeout=60,
        )
    return root


def rev_tree(root: Path, rev: str) -> str:
    """The tree object of `rev` in `root`, as git names it."""
    return subprocess.run(
        ["git", "rev-parse", f"{rev}^{{tree}}"],
        cwd=root,
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout.decode().strip()


def rev_head(root: Path, rev: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", f"{rev}^{{commit}}"],
        cwd=root,
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout.decode().strip()


def make_tar_gz(path: Path, files: dict[str, bytes]) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for rel, data in files.items():
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def make_zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for rel, data in files.items():
            zf.writestr(rel, data)
    return path


def sample_files() -> dict[str, bytes]:
    return {
        "README.md": b"# demo\n",
        "main.py": b"print('hello')\n",
        "data/raw.bin": bytes(range(64)),
    }


class TestResolveLocal:
    def test_a_directory_resolves_and_hashes(self, tmp_path: Path) -> None:
        dir = tmp_path / "proj"
        for rel, data in sample_files().items():
            path = dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        checkout = resolve_local(dir)
        assert checkout.checkout_dir == dir
        assert checkout.tree_hash.scheme == "plumb"
        assert checkout.tree_hash.digest == plumb_tree_hash(dir).digest
        assert checkout.source.kind == "local"
        assert checkout.source.location == str(dir)
        assert checkout.source.rev_resolved is None
        assert not checkout.source.rev_defaulted

    def test_a_missing_path_is_a_named_cause(self, tmp_path: Path) -> None:
        with pytest.raises(SourceNotFound):
            resolve_local(tmp_path / "nope")

    def test_a_file_is_not_a_directory(self, tmp_path: Path) -> None:
        path = tmp_path / "file.txt"
        path.write_bytes(b"x")
        with pytest.raises(SourceNotFound):
            resolve_local(path)

    def test_resolving_the_same_tree_twice_is_idempotent(self, tmp_path: Path) -> None:
        dir = tmp_path / "proj"
        for rel, data in sample_files().items():
            path = dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        first = resolve_local(dir)
        second = resolve_local(dir)
        assert first.tree_hash == second.tree_hash

    def test_the_size_cap_is_recorded_but_not_enforced(self, tmp_path: Path) -> None:
        dir = tmp_path / "proj"
        dir.mkdir()
        checkout = resolve_local(dir)
        assert checkout.source.size_cap_bytes == _DEFAULT_SIZE_CAP_BYTES


class TestResolveGit:
    def _origin(self, tmp_path: Path) -> tuple[Path, dict[str, str]]:
        repo = make_git_repo(
            tmp_path / "origin",
            [
                ("one", {"a.txt": b"one\n"}),
                ("two", {"a.txt": b"one\n", "b.txt": b"two\n"}),
            ],
        )
        sha1 = rev_head(repo, "HEAD~1")
        sha2 = rev_head(repo, "HEAD")
        subprocess.run(["git", "tag", "v1", sha1], cwd=repo, check=True, timeout=60)
        subprocess.run(["git", "branch", "dev", sha1], cwd=repo, check=True, timeout=60)
        return repo, {"sha1": sha1, "sha2": sha2, "tree1": rev_tree(repo, sha1), "tree2": rev_tree(repo, sha2)}

    def test_a_file_url_clones_and_pins_the_git_tree(self, tmp_path: Path) -> None:
        repo, revs = self._origin(tmp_path)
        checkout = resolve_git(repo.as_uri(), checkout_dir=tmp_path / "co")
        assert checkout.source.kind == "git"
        assert checkout.tree_hash.scheme == "git-tree"
        assert checkout.tree_hash.digest == revs["tree2"]
        assert (checkout.checkout_dir / "b.txt").read_bytes() == b"two\n"

    def test_the_default_rev_is_the_default_branch_and_is_recorded(
        self, tmp_path: Path
    ) -> None:
        repo, revs = self._origin(tmp_path)
        checkout = resolve_git(repo.as_uri(), checkout_dir=tmp_path / "co")
        assert checkout.source.rev_requested is None
        assert checkout.source.rev_defaulted
        assert checkout.source.rev_resolved == revs["sha2"]

    def test_a_branch_rev_is_honoured(self, tmp_path: Path) -> None:
        repo, revs = self._origin(tmp_path)
        checkout = resolve_git(repo.as_uri(), "dev", checkout_dir=tmp_path / "co")
        assert not checkout.source.rev_defaulted
        assert checkout.source.rev_resolved == revs["sha1"]
        assert checkout.tree_hash.digest == revs["tree1"]

    def test_a_tag_rev_is_honoured(self, tmp_path: Path) -> None:
        repo, revs = self._origin(tmp_path)
        checkout = resolve_git(repo.as_uri(), "v1", checkout_dir=tmp_path / "co")
        assert checkout.source.rev_resolved == revs["sha1"]
        assert checkout.tree_hash.digest == revs["tree1"]

    def test_a_sha_rev_is_honoured(self, tmp_path: Path) -> None:
        repo, revs = self._origin(tmp_path)
        checkout = resolve_git(repo.as_uri(), revs["sha1"], checkout_dir=tmp_path / "co")
        assert checkout.source.rev_resolved == revs["sha1"]
        assert checkout.tree_hash.digest == revs["tree1"]

    def test_an_unknown_rev_is_a_named_cause_and_cleans_up(self, tmp_path: Path) -> None:
        repo, _ = self._origin(tmp_path)
        with pytest.raises(RevNotFound):
            resolve_git(repo.as_uri(), "no-such-rev", checkout_dir=tmp_path / "co")
        # The failed clone is cleaned up so a retry with a valid rev succeeds.
        checkout = resolve_git(repo.as_uri(), checkout_dir=tmp_path / "co")
        assert checkout.tree_hash.digest == rev_tree(repo, "HEAD")

    def test_a_clone_failure_is_a_named_cause(self, tmp_path: Path) -> None:
        with pytest.raises(SourceNotFound):
            resolve_git((tmp_path / "missing").as_uri(), checkout_dir=tmp_path / "co")

    def test_resolving_the_same_rev_twice_is_idempotent(self, tmp_path: Path) -> None:
        repo, revs = self._origin(tmp_path)
        first = resolve_git(repo.as_uri(), checkout_dir=tmp_path / "co1")
        second = resolve_git(repo.as_uri(), checkout_dir=tmp_path / "co2")
        assert first.tree_hash == second.tree_hash
        assert first.tree_hash.digest == revs["tree2"]

    def test_the_size_cap_is_recorded(self, tmp_path: Path) -> None:
        repo, _ = self._origin(tmp_path)
        checkout = resolve_git(repo.as_uri(), checkout_dir=tmp_path / "co")
        assert checkout.source.size_cap_bytes == _DEFAULT_SIZE_CAP_BYTES


class TestResolveArchive:
    def test_a_tar_gz_extracts_with_the_plumb_tree_hash(self, tmp_path: Path) -> None:
        archive = make_tar_gz(tmp_path / "demo.tar.gz", sample_files())
        checkout = resolve_archive(archive, checkout_dir=tmp_path / "co")
        assert checkout.source.kind == "archive"
        assert checkout.source.location == str(archive)
        assert checkout.source.rev_resolved is None
        assert checkout.tree_hash.scheme == "plumb"
        assert checkout.tree_hash.digest == plumb_tree_hash(checkout.checkout_dir).digest
        assert (checkout.checkout_dir / "data" / "raw.bin").read_bytes() == bytes(range(64))

    def test_a_zip_extracts_with_the_plumb_tree_hash(self, tmp_path: Path) -> None:
        archive = make_zip(tmp_path / "demo.zip", sample_files())
        checkout = resolve_archive(archive, checkout_dir=tmp_path / "co")
        assert checkout.tree_hash.scheme == "plumb"
        assert checkout.tree_hash.digest == plumb_tree_hash(checkout.checkout_dir).digest

    def test_resolving_the_same_archive_twice_is_idempotent(self, tmp_path: Path) -> None:
        archive = make_tar_gz(tmp_path / "demo.tar.gz", sample_files())
        first = resolve_archive(archive, checkout_dir=tmp_path / "co1")
        second = resolve_archive(archive, checkout_dir=tmp_path / "co2")
        assert first.tree_hash == second.tree_hash

    def test_an_unsupported_extension_is_a_named_cause(self, tmp_path: Path) -> None:
        path = tmp_path / "demo.rar"
        path.write_bytes(b"\x00\x01")
        with pytest.raises(UnsupportedArchive):
            resolve_archive(path, checkout_dir=tmp_path / "co")

    def test_a_garbage_tar_gz_is_a_named_cause(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.tar.gz"
        path.write_bytes(b"this is not gzip")
        with pytest.raises(UnsupportedArchive):
            resolve_archive(path, checkout_dir=tmp_path / "co")

    def test_a_garbage_zip_is_a_named_cause(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.zip"
        path.write_bytes(b"this is not a zip")
        with pytest.raises(UnsupportedArchive):
            resolve_archive(path, checkout_dir=tmp_path / "co")

    def test_a_missing_archive_is_a_named_cause(self, tmp_path: Path) -> None:
        with pytest.raises(SourceNotFound):
            resolve_archive(tmp_path / "nope.tar.gz", checkout_dir=tmp_path / "co")

    def test_a_member_escaping_the_destination_is_rejected(self, tmp_path: Path) -> None:
        archive = make_zip(
            tmp_path / "evil.zip",
            {"../escape.txt": b"out", "ok.txt": b"in"},
        )
        with pytest.raises(UnsupportedArchive):
            resolve_archive(archive, checkout_dir=tmp_path / "co")

    def test_the_size_cap_is_recorded(self, tmp_path: Path) -> None:
        archive = make_tar_gz(tmp_path / "demo.tar.gz", sample_files())
        checkout = resolve_archive(archive, checkout_dir=tmp_path / "co")
        assert checkout.source.size_cap_bytes == _DEFAULT_SIZE_CAP_BYTES


class TestResolveGitClonesLandUnderTheRunArea:
    def test_a_git_source_equals_a_plumb_hand_checkout_only_by_scheme(
        self, tmp_path: Path
    ) -> None:
        # Git sources pin HEAD^{tree}; the same files resolved as a local dir
        # pin the plumb bytes framing. The scheme field is what reconciles them.
        repo = make_git_repo(
            tmp_path / "origin",
            [("one", {"a.txt": b"one\n"})],
        )
        checkout = resolve_git(repo.as_uri(), checkout_dir=tmp_path / "co")
        assert checkout.tree_hash.scheme == "git-tree"
        local = resolve_local(repo)
        assert local.tree_hash.scheme == "plumb"
        assert local.tree_hash.digest != checkout.tree_hash.digest