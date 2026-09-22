"""Tree hashing: the deterministic content address of a checkout (I1).

Two schemes land here, reconciled by one record type. The ``plumb`` scheme is
SHA-256 over the checkout's files, framed as sorted ``(relpath, kind, bytes)``
records — bytes and relative path only, so no mtime, inode, traversal order or
absolute path can leak into the digest. The ``git-tree`` scheme is the
repository's own tree object (``HEAD^{tree}``), which is the content address a
git source already carries.

The load-bearing assertions here are cross-process, mirroring
`tests/extract/test_determinism.py`:

- The seed control proves the children actually vary under different
  ``PYTHONHASHSEED`` values; without it, byte-identity across seeds is
  vacuous.
- The tree children are fresh interpreters computing the digest from scratch;
  identical digests under genuinely different seeds is evidence about the
  hasher, not about the plumbing.

Everything runs offline: the only subprocesses spawned are a local interpreter
and local ``git`` against a repo synthesized in a tmp dir.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from plumb.intake.causes import SourceNotFound
from plumb.intake.tree import git_tree_hash, plumb_tree_hash

_THIS_DIR = Path(__file__).parent
_SRC = _THIS_DIR.parents[2] / "src"

FIXED_SEEDS = ("0", "1", "12345")
SEEDS = FIXED_SEEDS + ("random",)

_CHILD_PROGRAM = """\
import sys

# argv[1] is tests/intake (the child imports the fixtures from the same module
# that will compare its output), argv[2] is src (so `plumb` resolves there).
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])

from test_tree import child_main

child_main(sys.argv[3], sys.argv[4])
"""


def child_main(payload: str, dir_arg: str) -> None:
    """Entry point for the spawned interpreter: the digest (or the probe).

    `probe` reports what this interpreter's `hash()` does — the one thing that
    *must* differ across the seeds, so a cross-seed byte-identity pass is
    evidence about the hasher rather than about plumbing that never varied.
    """
    if payload == "probe":
        seen = tuple(hash(word) for word in ("plumb", "tree", ".git"))
        sys.stdout.write(repr(seen))
        return
    if payload == "tree":
        sys.stdout.write(plumb_tree_hash(Path(dir_arg)).digest)
        return
    raise ValueError(f"unknown payload: {payload!r}")


def run_child(payload: str, dir_arg: str, *, hash_seed: str) -> str:
    """Run one fresh interpreter under `hash_seed`; return its stdout text."""
    env = {
        **os.environ,
        "PYTHONHASHSEED": hash_seed,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_PROGRAM, str(_THIS_DIR), str(_SRC), payload, dir_arg],
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (
        f"child failed (payload={payload!r}, dir={dir_arg!r}, seed={hash_seed!r}):\n"
        f"{result.stderr.decode('utf-8', 'replace')}"
    )
    return result.stdout.decode("utf-8")


def write_tree(root: Path, files: dict[str, bytes]) -> Path:
    """Create `files` (relpath → bytes) under `root`; returns `root`."""
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def sample_tree() -> dict[str, bytes]:
    """A small mixed tree: nested files, non-ASCII, and a binary file."""
    return {
        "README.md": b"# demo\nAUC 0.87 in the \xce\xbcohort.\n",
        "src/main.py": b"print('hello')\n",
        "src/data/raw.bin": bytes(range(256)),
        "results/out.txt": b"0.870\n",
    }


class TestSeedControl:
    """Proof the seeds reach the children — without it, cross-seed identity is air."""

    def test_the_hash_seed_really_varies_in_the_child(self) -> None:
        probes = {seed: run_child("probe", "", hash_seed=seed) for seed in FIXED_SEEDS}
        assert len(set(probes.values())) == len(FIXED_SEEDS), (
            "the children agree about hash() under different PYTHONHASHSEED values, "
            f"so the seed is not reaching them: {probes}"
        )


class TestPlumbTreeHash:
    """The `plumb` scheme: SHA-256 over sorted (relpath, kind, bytes)."""

    def test_stable_across_calls_in_one_process(self, tmp_path: Path) -> None:
        root = write_tree(tmp_path / "a", sample_tree())
        assert plumb_tree_hash(root) == plumb_tree_hash(root)

    def test_scheme_and_digest_shape(self, tmp_path: Path) -> None:
        digest = plumb_tree_hash(write_tree(tmp_path / "a", sample_tree()))
        assert digest.scheme == "plumb"
        assert len(digest.digest) == 64
        assert all(c in "0123456789abcdef" for c in digest.digest)

    def test_stable_across_processes_and_hash_seeds(self, tmp_path: Path) -> None:
        root = write_tree(tmp_path / "a", sample_tree())
        outputs = {seed: run_child("tree", str(root), hash_seed=seed) for seed in SEEDS}
        assert len(set(outputs.values())) == 1, (
            "plumb_tree_hash produced different digests under different "
            f"PYTHONHASHSEED values: { {s: len(o) for s, o in outputs.items()} }"
        )

    def test_the_child_digest_matches_this_process(self, tmp_path: Path) -> None:
        root = write_tree(tmp_path / "a", sample_tree())
        expected = plumb_tree_hash(root).digest
        assert run_child("tree", str(root), hash_seed="12345") == expected

    def test_touching_mtimes_does_not_change_the_hash(self, tmp_path: Path) -> None:
        root = write_tree(tmp_path / "a", sample_tree())
        before = plumb_tree_hash(root).digest
        when = 1_000_000_000
        for path in sorted(root.rglob("*")):
            if path.is_file():
                os.utime(path, (when, when))
        assert plumb_tree_hash(root).digest == before

    def test_the_git_directory_is_excluded(self, tmp_path: Path) -> None:
        plain = write_tree(tmp_path / "plain", sample_tree())
        with_git = write_tree(tmp_path / "with_git", sample_tree())
        write_tree(with_git / ".git", {
            "HEAD": b"ref: refs/heads/main\n",
            "objects/ab/cdef": b"\x00fake-object\xff",
            "config": b"[core]\n\trepositoryformatversion = 0\n",
        })
        assert plumb_tree_hash(with_git) == plumb_tree_hash(plain)

    def test_an_empty_directory_hashes_deterministically(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        first = plumb_tree_hash(empty)
        second = plumb_tree_hash(tmp_path / "also_empty")
        assert first.scheme == "plumb"
        assert first == second

    def test_a_content_change_changes_the_hash(self, tmp_path: Path) -> None:
        root = write_tree(tmp_path / "a", sample_tree())
        before = plumb_tree_hash(root).digest
        (root / "src" / "main.py").write_bytes(b"print('changed')\n")
        assert plumb_tree_hash(root).digest != before

    def test_build_order_does_not_matter(self, tmp_path: Path) -> None:
        files = sample_tree()
        reversed_order = write_tree(tmp_path / "a", dict(reversed(list(files.items()))))
        interleaved = {k: files[k] for k in list(files)[::2] + list(files)[1::2]}
        other = write_tree(tmp_path / "b", interleaved)
        assert plumb_tree_hash(reversed_order) == plumb_tree_hash(other)

    def test_the_hash_does_not_depend_on_where_the_tree_lives(self, tmp_path: Path) -> None:
        here = write_tree(tmp_path / "here" / "x" / "y", sample_tree())
        elsewhere = write_tree(tmp_path / "elsewhere", sample_tree())
        assert plumb_tree_hash(here) == plumb_tree_hash(elsewhere)

    def test_a_symlink_is_recorded_by_target_and_not_followed(self, tmp_path: Path) -> None:
        root = write_tree(tmp_path / "a", {"real.txt": b"payload\n"})
        (root / "link.txt").symlink_to("real.txt")
        linked = plumb_tree_hash(root).digest
        # Replacing the link with a regular file of the same name and the
        # *target's* bytes is a different tree: the link is recorded as its
        # target text, not followed.
        os.unlink(root / "link.txt")
        (root / "link.txt").write_bytes(b"payload\n")
        assert plumb_tree_hash(root).digest != linked


class TestGitTreeHash:
    """The `git-tree` scheme: the repository's own HEAD^{tree} object."""

    def _repo(self, tmp_path: Path, files: dict[str, bytes]) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, timeout=60)
        write_tree(repo, files)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=60)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Plumb Test",
                "-c",
                "user.email=test@plumb.local",
                "commit",
                "-q",
                "-m",
                "initial",
            ],
            cwd=repo,
            check=True,
            timeout=60,
        )
        return repo

    def test_scheme_and_digest_come_from_the_repo(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path, {"a.txt": b"one\n"})
        tree = git_tree_hash(repo)
        assert tree.scheme == "git-tree"
        raw = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=repo,
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout.decode().strip()
        assert tree.digest == raw

    def test_stable_for_the_same_rev(self, tmp_path: Path) -> None:
        repo = self._repo(tmp_path, {"a.txt": b"one\n"})
        assert git_tree_hash(repo) == git_tree_hash(repo)

    def test_changes_when_the_tree_changes_and_old_rev_recovers_old_digest(
        self, tmp_path: Path
    ) -> None:
        repo = self._repo(tmp_path, {"a.txt": b"one\n"})
        original = git_tree_hash(repo)
        (repo / "b.txt").write_bytes(b"two\n")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, timeout=60)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Plumb Test",
                "-c",
                "user.email=test@plumb.local",
                "commit",
                "-q",
                "-m",
                "second",
            ],
            cwd=repo,
            check=True,
            timeout=60,
        )
        changed = git_tree_hash(repo)
        assert changed.digest != original.digest
        first_rev = subprocess.run(
            ["git", "rev-parse", "HEAD~1"],
            cwd=repo,
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout.decode().strip()
        subprocess.run(["git", "checkout", "-q", first_rev], cwd=repo, check=True, timeout=60)
        assert git_tree_hash(repo) == original

    def test_a_non_repo_raises_a_named_cause(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        (plain / "f.txt").write_bytes(b"x")
        with pytest.raises(SourceNotFound):
            git_tree_hash(plain)

    def test_git_and_plumb_schemes_are_distinct_for_the_same_tree(
        self, tmp_path: Path
    ) -> None:
        # Reconciled by the scheme field, not by pretending the digests agree:
        # git's tree object and the plumb bytes framing are different content
        # addresses of the same files.
        repo = self._repo(tmp_path, {"a.txt": b"one\n"})
        git_tree = git_tree_hash(repo)
        plumb_tree = plumb_tree_hash(repo)
        assert git_tree.scheme != plumb_tree.scheme
        assert git_tree.digest != plumb_tree.digest


class TestTheDigestIsPinned:
    """Pin the empty-tree digest and one non-empty tree's digest.

    The empty tree is the anchor: the framing begins at zero records, so the
    digest is the plain SHA-256 of an empty stream. The non-empty pin keeps
    the framing honest — a reorder or a length-prefix change moves it.
    """

    def test_the_empty_tree_digest_is_pinned(self, tmp_path: Path) -> None:
        # The framing of an empty tree is just the empty stream.
        empty = tmp_path / "empty"
        empty.mkdir()
        assert plumb_tree_hash(empty).digest == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_a_sample_tree_digest_is_pinned(self, tmp_path: Path) -> None:
        root = write_tree(tmp_path / "a", sample_tree())
        digest = plumb_tree_hash(root)
        assert len(digest.digest) == 64
        # Cross-checked against an independent reimplementation of the framing
        # over the same bytes, so the pin is the framing and not a typo.
        hasher = hashlib.sha256()
        for rel, data in sorted(sample_tree().items()):
            rel_bytes = rel.encode("utf-8")
            hasher.update(len(rel_bytes).to_bytes(4, "big"))
            hasher.update(rel_bytes)
            hasher.update(b"f")
            hasher.update(len(data).to_bytes(8, "big"))
            hasher.update(data)
        assert digest.digest == hasher.hexdigest()