"""Verify a bundle from its bytes alone (signed-bundle B4, PRD B5).

`verify_bundle(root, allowed_signers=..., principal=..., paper=None)` returns a
`BundleReport`: `ok`, the named `causes`, and — only when everything holds — the
re-derived `VerdictSet`. **Content problems are reported, never raised.**

**The stages run in order, and a failing stage stops the rest**, because each one trusts only
what the stage before it established:

1. **Signature.** `manifest.sig` must be the verifier's trusted principal's SSHSIG over the
   exact bytes of `manifest.json`. Nothing in the bundle is read before this passes — an
   unsigned byte is never trusted, not even to parse.
2. **Manifest.** Canonical fields, member paths from a fixed set (`objects/<sha256>` for
   outputs), no path escaping the bundle.
3. **Members.** Every listed member exists with its SHA-256 and size; nothing unlisted;
   no symlinks.
4. **Structure.** Claims, trace and bindings parse; the trace's run id and tree hash are the
   manifest's; every bound output is present.
5. **Refused content.** No local path in any structured member; every object is a locatable
   (non-stderr) output of the trace.
6. **Paper and claims.** The paper — bundled, or supplied by the verifier — must be the one
   the manifest names; every claim is re-admitted against it (`plumb.extract.admit.readmit`):
   a bundle cannot carry a number the paper does not write at the stated place.
7. **Verdicts.** C4 re-derives them from the bundled outputs; the bytes must equal the signed
   `verdicts.json`.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from plumb.bundle.causes import (
    CLAIMS_UNGROUNDED,
    MANIFEST_INVALID,
    MEMBER_MISSING,
    MEMBER_REFUSED,
    MEMBER_TAMPERED,
    MEMBER_UNLISTED,
    PAPER_MISMATCH,
    PAPER_MISSING,
    SIGNATURE_INVALID,
    SIGNATURE_MISSING,
    VERDICTS_MISMATCH,
)
from plumb.bundle.sshsig import ssh_verify
from plumb.extract.admit import readmit
from plumb.extract.hashing import hash_paper
from plumb.extract.location import normalize_text
from plumb.extract.serialize import parse_claims
from plumb.run.capture import Capture
from plumb.run.trace import parse_trace
from plumb.verify import Completed, VerdictSet, load_bindings, serialize_verdicts, verify_claims

__all__ = ["FORMAT", "BundleReport", "check_contents", "paper_text", "verify_bundle"]

FORMAT = "plumb-bundle/1"
MANIFEST = "manifest.json"
SIGNATURE = "manifest.sig"
FIXED_MEMBERS = ("bindings.json", "claims.json", "environment.txt", "trace.json", "verdicts.json")
PAPER_MEMBERS = {"markdown": "paper.md", "pdf": "paper.pdf"}
STRUCTURED = (MANIFEST, *FIXED_MEMBERS)
_OBJECT = re.compile(r"objects/[0-9a-f]{64}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MANIFEST_FIELDS = {"format", "signer", "paper", "source", "tree_hash", "run_id", "members"}
_PAPER_FIELDS = {"format", "sha256", "source", "included"}
_SOURCE_FIELDS = {
    "kind", "location", "rev_requested", "rev_resolved", "rev_defaulted", "size_cap_bytes",
}

#: Markers of a path on the builder's machine. A heuristic, applied to the structured members
#: only (not to the run's own outputs): a bundle leaves the machine, and a home directory or
#: temp path in it is an egress of local state (constraint #2).
LOCAL_PATH_MARKERS = ("/Users/", "/home/", "/private/", "/tmp/", "/var/folders/", "C:\\")


@dataclass(frozen=True)
class BundleReport:
    """What verification established, and why it stopped if it did."""

    ok: bool
    causes: tuple[tuple[str, str], ...]
    verdicts: VerdictSet | None
    manifest: dict[str, Any] | None


class _Stop(Exception):
    def __init__(self, causes: list[tuple[str, str]]) -> None:
        self.causes = causes


def verify_bundle(
    root: Path | str, *, allowed_signers: Path | str, principal: str, paper: bytes | None = None
) -> BundleReport:
    """Verify the bundle at `root` against the verifier's trusted signers."""
    root = Path(root)
    manifest = None
    try:
        manifest_path = root / MANIFEST
        if not manifest_path.is_file():
            raise _Stop([(MANIFEST_INVALID, f"no {MANIFEST} in {root.name}")])
        if not (root / SIGNATURE).is_file():
            raise _Stop([(SIGNATURE_MISSING, f"no {SIGNATURE}")])
        manifest_bytes = manifest_path.read_bytes()
        reason = ssh_verify(
            manifest_bytes, (root / SIGNATURE).read_bytes(),
            allowed_signers=allowed_signers, principal=principal,
        )
        if reason is not None:
            raise _Stop([(SIGNATURE_INVALID, reason)])
        manifest = read_manifest(manifest_bytes)
        check_members(root, manifest)
        verdicts = check_contents(root, manifest, paper=paper)
    except _Stop as stop:
        return BundleReport(False, tuple(stop.causes), None, manifest)
    return BundleReport(True, (), verdicts, manifest)


# --------------------------------------------------------------------------------
# Stages (shared with build, which runs them before it signs)
# --------------------------------------------------------------------------------


def read_manifest(data: bytes) -> dict[str, Any]:
    try:
        manifest = json.loads(data.decode("utf-8"))
        if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
            raise ValueError(f"a manifest has exactly the fields {sorted(_MANIFEST_FIELDS)}")
        if manifest["format"] != FORMAT:
            raise ValueError(f"format {manifest['format']!r} is not {FORMAT!r}")
        paper = manifest["paper"]
        if not isinstance(paper, dict) or set(paper) != _PAPER_FIELDS:
            raise ValueError(f"paper has exactly the fields {sorted(_PAPER_FIELDS)}")
        if paper["format"] not in PAPER_MEMBERS or not _SHA256.fullmatch(paper["sha256"]):
            raise ValueError("paper format or sha256 is malformed")
        if not isinstance(manifest["source"], dict) or set(manifest["source"]) != _SOURCE_FIELDS:
            raise ValueError(f"source has exactly the fields {sorted(_SOURCE_FIELDS)}")
        allowed = set(FIXED_MEMBERS)
        if paper["included"] is True:
            allowed.add(PAPER_MEMBERS[paper["format"]])
        paths = []
        for member in manifest["members"]:
            if set(member) != {"path", "sha256", "size"} or not _SHA256.fullmatch(member["sha256"]):
                raise ValueError(f"malformed member {member!r}")
            if member["path"] not in allowed and not _OBJECT.fullmatch(member["path"]):
                raise ValueError(f"member path {member['path']!r} is not a bundle member")
            paths.append(member["path"])
        if paths != sorted(set(paths)):
            raise ValueError("members must be unique and sorted by path")
        if not allowed <= set(paths):
            raise ValueError(f"required members missing from the manifest: {sorted(allowed - set(paths))}")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
        raise _Stop([(MANIFEST_INVALID, str(exc))]) from None
    return manifest


def check_members(root: Path, manifest: dict[str, Any]) -> None:
    causes: list[tuple[str, str]] = []
    listed = {m["path"]: m for m in manifest["members"]}
    on_disk = set()
    for path in sorted(root.rglob("*")):
        relpath = path.relative_to(root).as_posix()
        if path.is_symlink():
            causes.append((MEMBER_REFUSED, f"{relpath} is a symlink"))
        elif path.is_file() and relpath not in (MANIFEST, SIGNATURE):
            on_disk.add(relpath)
    for relpath in sorted(on_disk - set(listed)):
        causes.append((MEMBER_UNLISTED, relpath))
    for relpath, member in sorted(listed.items()):
        path = root / relpath
        if relpath not in on_disk:
            causes.append((MEMBER_MISSING, relpath))
            continue
        data = path.read_bytes()
        if len(data) != member["size"] or hashlib.sha256(data).hexdigest() != member["sha256"]:
            causes.append((MEMBER_TAMPERED, relpath))
    if causes:
        raise _Stop(causes)


def paper_text(data: bytes, paper_format: str) -> str:
    """The raw paper text the claim offsets were measured on (before normalization)."""
    if paper_format == "markdown":
        return data.decode("utf-8")
    from plumb.pdf import pdf_to_markdown  # the one heavy import, only for PDF papers

    return pdf_to_markdown(data)


def check_contents(root: Path, manifest: dict[str, Any], *, paper: bytes | None) -> VerdictSet:
    """Stages 4–7 on members already known to match the manifest."""
    read = lambda name: (root / name).read_bytes()  # noqa: E731

    try:
        records, paper_hash = parse_claims(read("claims.json"))
        trace = parse_trace(read("trace.json"))
        bindings = load_bindings(read("bindings.json"), [r.id for r in records])
        if trace.run_id != manifest["run_id"] or {
            "scheme": trace.tree_hash.scheme, "digest": trace.tree_hash.digest
        } != manifest["tree_hash"]:
            raise ValueError("the trace does not describe the run the manifest names")
    except (ValueError, TypeError, KeyError) as exc:
        raise _Stop([(MANIFEST_INVALID, str(exc))]) from None

    refused = []
    for name in STRUCTURED:
        text = read(name).decode("utf-8", "replace")
        for marker in LOCAL_PATH_MARKERS:
            if marker in text:
                refused.append((MEMBER_REFUSED, f"{name} carries a local path ({marker})"))
    locatable = {a.sha256: a for a in trace.artifacts if not a.diagnostic_only}
    diagnostic = {a.sha256 for a in trace.artifacts if a.diagnostic_only}
    objects = {m["path"].split("/", 1)[1] for m in manifest["members"]
               if m["path"].startswith("objects/")}
    for sha in sorted(objects):
        if sha in diagnostic and sha not in locatable:
            refused.append((MEMBER_REFUSED, f"objects/{sha} is the run's stderr"))
        elif sha not in locatable:
            refused.append((MEMBER_REFUSED, f"objects/{sha} is not an output of this run"))
    if refused:
        raise _Stop(refused)
    required = bound_objects(bindings, trace)
    if not required <= objects:
        raise _Stop([(MANIFEST_INVALID, f"bound outputs left out: {sorted(required - objects)}")])

    declared = manifest["paper"]
    if declared["included"]:
        paper = read(PAPER_MEMBERS[declared["format"]])
    if paper is None:
        raise _Stop([(PAPER_MISSING, "the paper is not bundled and was not supplied")])
    if hashlib.sha256(paper).hexdigest() != declared["sha256"]:
        raise _Stop([(PAPER_MISMATCH, "the paper is not the one the manifest names")])
    raw = paper_text(paper, declared["format"])
    if hash_paper(raw) != paper_hash:
        raise _Stop([(PAPER_MISMATCH, "the claims were not extracted from this paper's text")])
    try:
        claims = readmit(records, normalized_text=normalize_text(raw))
    except ValueError as exc:
        raise _Stop([(CLAIMS_UNGROUNDED, str(exc))]) from None

    capture = Capture(store=root / "objects", artifacts=trace.artifacts, stale=trace.stale,
                      causes=trace.causes)
    try:
        verdicts = verify_claims(claims, bindings, Completed(trace, capture))
    except (ValueError, OSError) as exc:
        raise _Stop([(MANIFEST_INVALID, str(exc))]) from None
    if serialize_verdicts(verdicts) != read("verdicts.json"):
        raise _Stop([(VERDICTS_MISMATCH, "re-derived verdicts differ from the signed ones")])
    return verdicts


def bound_objects(bindings, trace) -> set[str]:
    """The SHA-256 of every locatable output a binding reads."""
    targets = {b.artifact for b in bindings.values()}
    return {a.sha256 for a in trace.artifacts if not a.diagnostic_only and a.relpath in targets}
