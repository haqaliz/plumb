"""Deterministic tar packaging for a bundle, and safe unpacking.

`pack(root, out)` writes every member into one archive — sorted, mtime 0, uid/gid 0, no
uname/gname, mode 0o644 — so two packs of the same bundle are byte-identical (`.tar`, `.tar.gz`
and `.tgz`; gzip is written with `mtime=0`, no filename). `unpack(archive, dest)` is the trust
boundary: an archive is untrusted input, so a path outside `dest`, an absolute path, and any
entry that is not a regular file (symlink, hardlink, device) are refused with a named cause and
nothing is written for the whole archive beyond what it already wrote.
"""

from __future__ import annotations

import gzip
import io
from pathlib import Path
import shutil
import tarfile

from plumb.bundle.causes import MANIFEST_INVALID, MEMBER_REFUSED, BundleRefused

__all__ = ["is_archive", "pack", "unpack"]

_MANIFEST = "manifest.json"
_SUFFIXES = (".tar", ".tar.gz", ".tgz")


def is_archive(path: Path | str) -> bool:
    """A readable path whose name ends in a supported archive suffix."""
    candidate = Path(path)
    return candidate.is_file() and candidate.name.lower().endswith(_SUFFIXES)


def pack(root: Path | str, out: Path | str) -> Path:
    """Write the bundle at `root` into the archive at `out`; deterministic bytes."""
    root, out = Path(root), Path(out)
    if not (root / _MANIFEST).is_file():
        raise BundleRefused(f"{root} is not a bundle: no {_MANIFEST}", MANIFEST_INVALID)
    files = sorted(p for p in root.rglob("*") if p.is_file())

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for path in files:
            data = path.read_bytes()
            info = tarfile.TarInfo(path.relative_to(root).as_posix())
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    payload = raw.getvalue()
    if out.name.lower().endswith((".tar.gz", ".tgz")):
        compressed = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as gz:
            gz.write(payload)
        payload = compressed.getvalue()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload)
    return out


def unpack(archive: Path | str, dest: Path | str) -> Path:
    """Extract the archive into `dest`, refusing anything that is not a plain file inside it."""
    archive, dest = Path(archive), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    try:
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                if member.isdir():
                    continue
                if not member.isfile():
                    raise BundleRefused(
                        f"{archive.name}: refusing a non-file entry {member.name!r}",
                        MEMBER_REFUSED,
                    )
                name = Path(member.name)
                target = (dest / name).resolve()
                if name.is_absolute() or ".." in name.parts or root not in target.parents:
                    raise BundleRefused(
                        f"{archive.name}: refusing a path outside the bundle: {member.name!r}",
                        MEMBER_REFUSED,
                    )
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                with open(target, "wb") as handle:
                    shutil.copyfileobj(source, handle)
    except tarfile.TarError as exc:
        raise BundleRefused(f"{archive} is not a readable tar: {exc}", MANIFEST_INVALID) from exc
    return dest
