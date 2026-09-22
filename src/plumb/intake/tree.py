"""Deterministic tree hashing for checkouts (I1).

Two schemes, one record type:

- **``plumb``** — SHA-256 over the checkout's files, framed as sorted
  ``(relpath, kind, bytes)`` records. Input is the relative path and the file's
  bytes only: no mtimes, no inode numbers, no traversal order, no absolute
  paths, so the digest is stable across checkouts and machines. ``.git`` is
  excluded — it is the version-control bookkeeping of the source, not part of
  the tree being pinned. A symlink is recorded by its target text and never
  followed, so the hash cannot escape the tree or depend on the target's
  contents.
- **``git-tree``** — the repository's own tree object (``HEAD^{tree}``), read
  via ``git rev-parse`` in a subprocess. This is the content address a git
  source already carries; the ``scheme`` field reconciles it with the ``plumb``
  scheme in one record, and replay uses whichever scheme the source used.

Determinism is pinned in `tests/intake/test_tree.py`: byte identity across
processes under varying ``PYTHONHASHSEED`` (with the seed-reaches-the-child
control), and mtime-insensitivity. Everything here is offline: the only
subprocess is local ``git`` against a repository on the user's compute.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess

from plumb.intake.causes import SourceNotFound

__all__ = ["TreeHash", "git_tree_hash", "plumb_tree_hash"]

#: Kinds carried in a hash record: ``f`` regular file, ``l`` symlink target.
_KIND_FILE = b"f"
_KIND_LINK = b"l"


@dataclass(frozen=True)
class TreeHash:
    """A pinned content address of a checkout.

    ``scheme`` names how the digest was produced: ``"plumb"`` (deterministic
    bytes framing, see `plumb_tree_hash`) or ``"git-tree"`` (the repository's
    own tree object, see `git_tree_hash`).
    """

    scheme: str
    digest: str


def _iter_entries(root: Path) -> list[tuple[str, bytes, bytes]]:
    """Every file and symlink under `root`, as (relpath, kind, payload).

    Sorted by relative path so traversal order never reaches the digest.
    ``.git`` is pruned at every depth. Symlinks are read as their target text,
    never followed — a symlinked directory is not descended into.
    """
    entries: list[tuple[str, bytes, bytes]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        kept: list[str] = []
        for name in dirnames:
            path = Path(dirpath, name)
            if path.is_symlink():
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                entries.append((rel, _KIND_LINK, os.readlink(path).encode()))
            else:
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            path = Path(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if path.is_symlink():
                entries.append((rel, _KIND_LINK, os.readlink(path).encode()))
            else:
                entries.append((rel, _KIND_FILE, path.read_bytes()))
    entries.sort(key=lambda entry: entry[0])
    return entries


def plumb_tree_hash(dir: Path) -> TreeHash:
    """SHA-256 over the tree's sorted ``(relpath, kind, bytes)`` records.

    The framing is length-prefixed on both the relative path and the payload,
    so the records parse unambiguously and no concatenation can alias two
    different trees. Only the relative path and the bytes enter the digest.
    """
    hasher = hashlib.sha256()
    for rel, kind, payload in _iter_entries(dir):
        rel_bytes = rel.encode("utf-8")
        hasher.update(len(rel_bytes).to_bytes(4, "big"))
        hasher.update(rel_bytes)
        hasher.update(kind)
        hasher.update(len(payload).to_bytes(8, "big"))
        hasher.update(payload)
    return TreeHash(scheme="plumb", digest=hasher.hexdigest())


def git_tree_hash(dir: Path) -> TreeHash:
    """The repository's own ``HEAD^{tree}`` object, as a ``git-tree`` record.

    Fails with the named cause `SourceNotFound` when `dir` is not a git
    repository — never a silent or ambiguous failure. Stable for the same rev:
    checking out another rev changes the tree object, and checking out the
    first rev again recovers the original digest.
    """
    result = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=str(dir),
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise SourceNotFound(f"not a git repository at {dir} ({detail})")
    digest = result.stdout.decode("utf-8").strip()
    if not digest or not all(c in "0123456789abcdef" for c in digest) or len(digest) < 40:
        raise SourceNotFound(f"unusable tree object from git at {dir}: {digest!r}")
    return TreeHash(scheme="git-tree", digest=digest)