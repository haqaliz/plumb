"""`plumb bundle` — verify, inspect and pack a signed bundle (issue #20).

The same `verify_bundle` the engine uses, reachable without importing Python: a third party
checks a directory or an archive, gets one line per named cause, and exits 1 when it does not
hold. `inspect` deliberately does not verify — it reads unauthenticated manifest fields and says
so. `pack` produces the transport artifact: deterministic bytes, one archive.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

from plumb.bundle import BundleRefused, verify_bundle
from plumb.bundle import causes as C
from plumb.bundle.pack import is_archive, pack, unpack
from plumb.bundle.verify import read_manifest

__all__ = ["cmd_bundle_inspect", "cmd_bundle_pack", "cmd_bundle_verify"]

_JSON = {"sort_keys": True, "ensure_ascii": False, "separators": (",", ":")}


def _fail(cause: str, detail: str) -> int:
    print(f"plumb bundle: {cause}: {detail}", file=sys.stderr)
    return 1


class _Root:
    """The bundle directory, unpacked to a temp dir first when the input is an archive."""

    def __enter__(self) -> Path:
        if is_archive(self.path):
            self._tmp = tempfile.TemporaryDirectory(prefix="plumb-bundle-")
            try:
                return unpack(self.path, Path(self._tmp.name))
            except BaseException:
                self._tmp.cleanup()
                raise
        return self.path

    def __exit__(self, *exc) -> None:
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()

    def __init__(self, path: Path) -> None:
        self.path = path


def cmd_bundle_verify(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Verify a bundle against the verifier's own allowed signers."""
    allowed = Path(args.allowed_signers)
    if not allowed.is_file():
        return _fail(C.MANIFEST_INVALID, f"no allowed-signers file at {allowed}")
    paper = None
    if args.paper is not None:
        try:
            paper = Path(args.paper).read_bytes()
        except OSError as exc:
            return _fail(C.PAPER_MISSING, f"{args.paper} is not readable: {exc}")
    try:
        with _Root(Path(args.bundle)) as root:
            report = verify_bundle(
                root, allowed_signers=allowed, principal=args.principal, paper=paper,
            )
    except BundleRefused as exc:
        return _fail(exc.cause or C.MANIFEST_INVALID, str(exc))
    if not report.ok:
        for cause, detail in report.causes:
            print(f"plumb bundle: {cause}: {detail}", file=sys.stderr)
        return 1
    manifest = report.manifest
    claims = len(report.verdicts.verdicts)
    if args.json:
        document = {
            "ok": True, "signer": manifest["signer"], "run_id": manifest["run_id"],
            "claims": claims, "members": len(manifest["members"]),
            "created": manifest.get("created"), "causes": [],
        }
        print(json.dumps(document, **_JSON))
    else:
        print(f"bundle ok: {claims} claims, {len(manifest['members'])} members, "
              f"signer {manifest['signer']}")
    return 0


def cmd_bundle_inspect(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Read the manifest's declared fields — no signature check, and the output says so."""
    try:
        with _Root(Path(args.bundle)) as root:
            path = root / "manifest.json"
            if not path.is_file():
                raise BundleRefused(f"{args.bundle} is not a bundle: no manifest.json",
                                    C.MANIFEST_INVALID)
            manifest = read_manifest(path.read_bytes())
    except BundleRefused as exc:
        return _fail(exc.cause or C.MANIFEST_INVALID, str(exc))
    except (OSError, ValueError) as exc:
        return _fail(C.MANIFEST_INVALID, str(exc))

    created = manifest.get("created")
    document = {
        "format": manifest["format"], "signer": manifest["signer"],
        "signature_checked": False, "paper": manifest["paper"]["sha256"],
        "paper_included": manifest["paper"]["included"],
        "source": manifest["source"]["location"],
        "tree_hash": manifest["tree_hash"]["digest"], "run_id": manifest["run_id"],
        "created": created, "members": len(manifest["members"]),
    }
    if args.json:
        print(json.dumps(document, **_JSON))
        return 0
    print(f"format: {document['format']}")
    print(f"signer: {document['signer']}")
    print("signature: not checked (run `plumb bundle verify`)")
    print(f"paper: {document['paper']} included={'yes' if document['paper_included'] else 'no'}")
    print(f"source: {document['source']}")
    print(f"tree: {document['tree_hash']}")
    print(f"run: {document['run_id']}")
    print(f"created: {created if created is not None else 'none'}")
    print(f"members: {document['members']}")
    return 0


def cmd_bundle_pack(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Write a deterministic archive of the bundle directory."""
    try:
        out = pack(Path(args.bundle), Path(args.out))
    except BundleRefused as exc:
        return _fail(exc.cause or C.MANIFEST_INVALID, str(exc))
    print(out)
    return 0
