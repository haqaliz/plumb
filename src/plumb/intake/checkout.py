"""Source resolution to pinned checkouts (I2).

Three resolvers, one record type:

- `resolve_local(path)` — pins an existing directory in place (the user's own
  compute, nothing copied), hashed with the deterministic plumb bytes framing.
- `resolve_git(url, rev=None)` — clones to a checkout under the run area,
  checks out `rev` (default: the repository's default branch, recorded as
  such), and pins the repository's own tree object (`HEAD^{tree}`).
- `resolve_archive(path)` — extracts a tar.gz or zip to a checkout under the
  run area, hashed with the plumb framing.

Every failure resolves to a named cause — `SourceNotFound`, `RevNotFound`,
`UnsupportedArchive` — never a silent drop. The size cap is recorded on every
source record but deliberately not enforced here; enforcement is a named
follow-on. Everything is offline-capable: git runs against `file://` URLs and
archives are read in-process, all on the user's compute.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import zipfile

from plumb.intake.causes import RevNotFound, SourceNotFound, UnsupportedArchive
from plumb.intake.tree import TreeHash, git_tree_hash, plumb_tree_hash

__all__ = [
    "Checkout",
    "SourceRecord",
    "resolve_archive",
    "resolve_git",
    "resolve_local",
]

#: Recorded on every source, not enforced yet (named follow-on: archive bomb
#: and huge-checkout limits).
_DEFAULT_SIZE_CAP_BYTES = 1 << 30

_GIT_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class SourceRecord:
    """What a checkout came from, and how it was pinned."""

    kind: str  # "local" | "git" | "archive"
    location: str  # the path or URL the caller handed us
    rev_requested: str | None  # what the caller asked for; None when absent
    rev_resolved: str | None  # the actual rev pinned (git SHA); else None
    rev_defaulted: bool  # True when the default branch was used without asking
    size_cap_bytes: int  # recorded, not enforced (named follow-on)


@dataclass(frozen=True)
class Checkout:
    """A pinned checkout: where the code lives, and its content address."""

    checkout_dir: Path
    tree_hash: TreeHash
    source: SourceRecord


def resolve_local(path: Path | str) -> Checkout:
    """Pin an existing local directory in place, hashed with the plumb scheme."""
    directory = Path(path)
    if not directory.is_dir():
        raise SourceNotFound(f"no such directory: {directory}")
    return Checkout(
        checkout_dir=directory,
        tree_hash=plumb_tree_hash(directory),
        source=SourceRecord(
            kind="local",
            location=str(directory),
            rev_requested=None,
            rev_resolved=None,
            rev_defaulted=False,
            size_cap_bytes=_DEFAULT_SIZE_CAP_BYTES,
        ),
    )


def resolve_git(
    url: str, rev: str | None = None, *, checkout_dir: Path | str | None = None
) -> Checkout:
    """Clone `url` and pin `rev` (default: the default branch) as ``git-tree``."""
    dest = _default_checkout_dir(url, checkout_dir, is_archive=False)
    if dest.exists() and any(dest.iterdir()):
        raise SourceNotFound(
            f"destination already exists and is not empty: {dest} — refusing to clone over it"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    clone = subprocess.run(
        ["git", "clone", "--quiet", url, str(dest)],
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
    )
    if clone.returncode != 0:
        detail = clone.stderr.decode("utf-8", "replace").strip()
        shutil.rmtree(dest, ignore_errors=True)
        raise SourceNotFound(f"git clone failed for {url!r}: {detail}")
    try:
        if rev is not None:
            _checkout_rev(dest, url, rev)
        tree_hash = git_tree_hash(dest)
        rev_resolved = _git_rev(dest, "HEAD")
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return Checkout(
        checkout_dir=dest,
        tree_hash=tree_hash,
        source=SourceRecord(
            kind="git",
            location=url,
            rev_requested=rev,
            rev_resolved=rev_resolved,
            rev_defaulted=rev is None,
            size_cap_bytes=_DEFAULT_SIZE_CAP_BYTES,
        ),
    )


def resolve_archive(
    path: Path | str, *, checkout_dir: Path | str | None = None
) -> Checkout:
    """Extract a tar.gz or zip to a checkout, hashed with the plumb scheme."""
    archive = Path(path)
    if not archive.is_file():
        raise SourceNotFound(f"no such archive: {archive}")
    dest = _default_checkout_dir(archive, checkout_dir, is_archive=True)
    if dest.exists() and any(dest.iterdir()):
        raise SourceNotFound(
            f"destination already exists and is not empty: {dest} — refusing to extract over it"
        )
    dest.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    if name.endswith(".zip"):
        _extract_zip(archive, dest)
    elif name.endswith((".tar.gz", ".tgz")):
        _extract_tar(archive, dest)
    else:
        shutil.rmtree(dest, ignore_errors=True)
        raise UnsupportedArchive(
            f"unsupported archive format: {archive.name} "
            "(supported: .tar.gz, .tgz, .zip)"
        )
    return Checkout(
        checkout_dir=dest,
        tree_hash=plumb_tree_hash(dest),
        source=SourceRecord(
            kind="archive",
            location=str(archive),
            rev_requested=None,
            rev_resolved=None,
            rev_defaulted=False,
            size_cap_bytes=_DEFAULT_SIZE_CAP_BYTES,
        ),
    )


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


def _slug(name: str) -> str:
    """A filesystem-safe name derived from the source's tail."""
    tail = name.rstrip("/").split("/")[-1]
    if tail.endswith(".git"):
        tail = tail[: -len(".git")]
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in tail) or "checkout"


def _default_checkout_dir(
    source: Path | str, explicit: Path | str | None, *, is_archive: bool
) -> Path:
    if explicit is not None:
        return Path(explicit)
    source_path = Path(str(source))
    if is_archive:
        slug = source_path.stem
    else:
        slug = _slug(str(source))
    return Path("checkouts") / slug


def _checkout_rev(repo: Path, url: str, rev: str) -> None:
    # Resolve first so a bad rev is a named `RevNotFound`, then detach at the
    # exact SHA. A fresh clone holds remote branches as refs/remotes/origin/*,
    # so a branch name resolves there when it is not a local branch.
    resolved = _git_rev(repo, rev)
    if resolved is None:
        raise RevNotFound(f"revision {rev!r} not found in {url}")
    checkout = subprocess.run(
        ["git", "checkout", "--quiet", "--detach", resolved],
        cwd=str(repo),
        capture_output=True,
        timeout=_GIT_TIMEOUT_SECONDS,
        check=False,
    )
    if checkout.returncode != 0:
        detail = checkout.stderr.decode("utf-8", "replace").strip()
        raise RevNotFound(f"could not check out {rev!r} in {url}: {detail}")


def _git_rev(repo: Path, rev: str) -> str | None:
    """Resolve `rev` to a commit SHA in `repo`, or None when unknown."""
    for candidate in (f"{rev}^{{commit}}", f"refs/remotes/origin/{rev}^{{commit}}"):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", candidate],
            cwd=str(repo),
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8").strip()
    return None


def _safe_target(dest: Path, member_name: str) -> Path:
    """Reject archive members that would escape the destination directory."""
    dest_root = os.path.abspath(dest)
    target = os.path.abspath(os.path.join(dest_root, member_name))
    if os.path.commonpath([dest_root, target]) != dest_root:
        raise UnsupportedArchive(
            f"archive member escapes the destination: {member_name!r}"
        )
    return Path(target)


def _extract_tar(archive: Path, dest: Path) -> None:
    try:
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf.getmembers():
                if member.isdir():
                    continue
                target = _safe_target(dest, member.name)
                if member.issym() or member.islnk():
                    _check_link_target(dest, target, member.linkname)
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = tf.extractfile(member)
                if extracted is None:
                    continue
                target.write_bytes(extracted.read())
    except (tarfile.TarError, OSError, ValueError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise UnsupportedArchive(f"not a readable tar.gz: {archive} ({exc})") from exc


def _extract_zip(archive: Path, dest: Path) -> None:
    try:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.filename.endswith("/"):
                    continue
                target = _safe_target(dest, info.filename)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    link_target = zf.read(info).decode("utf-8", "surrogateescape")
                    _check_link_target(dest, target, link_target)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(info))
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise UnsupportedArchive(f"not a readable zip: {archive} ({exc})") from exc


def _check_link_target(dest: Path, target: Path, link_target: str) -> None:
    """Reject a symlink member whose target escapes the destination."""
    resolved = os.path.normpath(os.path.join(target.parent, link_target))
    dest_root = os.path.abspath(dest)
    if os.path.commonpath([dest_root, os.path.abspath(resolved)]) != dest_root:
        raise UnsupportedArchive(
            f"archive symlink escapes the destination: {link_target!r}"
        )