"""Build and sign a bundle (signed-bundle B3, PRD B2–B4).

`build_bundle(out, ...)` writes the members, derives the verdicts itself (C4 over the given
claims, bindings and run — a bundle never carries verdicts it did not re-derive), runs the
same checks `verify_bundle` runs, and only then writes the manifest and signs it. A bundle
that would not verify is never signed: `BundleRefused` names the cause and the half-built
directory is removed.

**Minimal disclosure** (constraint #2): the only captured outputs included are the ones a
binding reads; stderr never is. The trace still lists every output's hash, so the run id
stays checkable. The paper is included only when asked (`include_paper`); otherwise it is
named by its SHA-256 and the verifier supplies it.

**Deterministic:** canonical JSON, sorted members, no timestamp anywhere, and a deterministic
signature — the same inputs and key give the same bytes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from plumb.bundle.causes import BundleRefused
from plumb.bundle.verify import (
    FORMAT,
    MANIFEST,
    PAPER_MEMBERS,
    SIGNATURE,
    _Stop,
    bound_objects,
    check_contents,
    check_members,
    paper_text,
    read_manifest,
)
from plumb.extract.admit import readmit
from plumb.extract.hashing import hash_paper
from plumb.extract.location import normalize_text
from plumb.extract.serialize import parse_claims, serialize_claims
from plumb.intake.checkout import SourceRecord
from plumb.run.capture import Capture
from plumb.run.trace import RunTrace, parse_trace, serialize_trace
from plumb.verify import Completed, load_bindings, serialize_verdicts, verify_claims

__all__ = ["add_member_and_resign", "build_bundle", "rebuild_bundle", "resign"]

_JSON = {"sort_keys": True, "ensure_ascii": False, "separators": (",", ":"), "allow_nan": False}


def build_bundle(
    out: Path | str,
    *,
    claims,
    paper: bytes,
    paper_format: str,
    paper_source: str | None,
    include_paper: bool,
    bindings: bytes,
    trace: RunTrace,
    capture: Capture,
    environment: str,
    source: SourceRecord,
    signer,
) -> Path:
    """Write, check and sign the bundle at `out`; refuse rather than sign a bad one."""
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise BundleRefused(f"{out} exists and is not empty; a bundle is written fresh")
    if paper_format not in PAPER_MEMBERS:
        raise BundleRefused(f"paper_format must be one of {sorted(PAPER_MEMBERS)}")

    claims = list(claims)
    raw = paper_text(paper, paper_format)
    loaded = load_bindings(bindings, [c.id for c in claims])
    verdicts = verify_claims(claims, loaded, Completed(trace, capture))
    members: dict[str, bytes] = {
        "claims.json": serialize_claims(claims, paper_hash=hash_paper(raw)),
        "bindings.json": bindings,
        "trace.json": serialize_trace(trace),
        "verdicts.json": serialize_verdicts(verdicts),
        "environment.txt": environment.encode("utf-8"),
    }
    by_sha = {a.sha256: a for a in capture.locatable}
    for sha in sorted(bound_objects(loaded, trace)):
        members[f"objects/{sha}"] = capture.read(by_sha[sha])
    if include_paper:
        members[PAPER_MEMBERS[paper_format]] = paper

    manifest = {
        "format": FORMAT,
        "signer": signer.principal,
        "paper": {"format": paper_format, "sha256": hashlib.sha256(paper).hexdigest(),
                  "source": paper_source, "included": include_paper},
        "source": {"kind": source.kind, "location": source.location,
                   "rev_requested": source.rev_requested, "rev_resolved": source.rev_resolved,
                   "rev_defaulted": source.rev_defaulted,
                   "size_cap_bytes": source.size_cap_bytes},
        "tree_hash": {"scheme": trace.tree_hash.scheme, "digest": trace.tree_hash.digest},
        "run_id": trace.run_id,
        "members": [],
    }
    out.mkdir(parents=True, exist_ok=True)
    try:
        for relpath, data in members.items():
            (out / relpath).parent.mkdir(parents=True, exist_ok=True)
            (out / relpath).write_bytes(data)
        _write_manifest(out, manifest)
        checked = read_manifest((out / MANIFEST).read_bytes())
        check_members(out, checked)
        check_contents(out, checked, paper=None if include_paper else paper)
    except _Stop as stop:
        shutil.rmtree(out)
        cause, detail = stop.causes[0]
        raise BundleRefused(f"{cause}: {detail}", cause) from None
    (out / SIGNATURE).write_bytes(signer.sign((out / MANIFEST).read_bytes()))
    return out


def rebuild_bundle(src: Path | str, out: Path | str, *, signer, paper: bytes | None = None) -> Path:
    """Build a fresh bundle from an existing bundle's members (re-signing it under `signer`)."""
    src = Path(src)
    manifest = read_manifest((src / MANIFEST).read_bytes())
    declared = manifest["paper"]
    if declared["included"]:
        paper = (src / PAPER_MEMBERS[declared["format"]]).read_bytes()
    if paper is None:
        raise BundleRefused("the source bundle does not include its paper; supply it")
    records, _ = parse_claims((src / "claims.json").read_bytes())
    claims = readmit(records, normalized_text=normalize_text(paper_text(paper, declared["format"])))
    trace = parse_trace((src / "trace.json").read_bytes())
    capture = Capture(store=src / "objects", artifacts=trace.artifacts, stale=trace.stale,
                      causes=trace.causes)
    return build_bundle(
        out, claims=claims, paper=paper, paper_format=declared["format"],
        paper_source=declared["source"], include_paper=declared["included"],
        bindings=(src / "bindings.json").read_bytes(), trace=trace, capture=capture,
        environment=(src / "environment.txt").read_text(encoding="utf-8"),
        source=SourceRecord(**manifest["source"]), signer=signer,
    )


def resign(root: Path | str, signer) -> None:
    """Re-list whatever is on disk and sign it — no checks. For tests of `verify_bundle`."""
    root = Path(root)
    manifest = json.loads((root / MANIFEST).read_bytes())
    _write_manifest(root, manifest)
    (root / SIGNATURE).write_bytes(signer.sign((root / MANIFEST).read_bytes()))


def add_member_and_resign(root: Path | str, relpath: str, data: bytes, signer) -> None:
    """Write `relpath` into the bundle and re-sign — no checks. For tests of `verify_bundle`."""
    root = Path(root)
    (root / relpath).parent.mkdir(parents=True, exist_ok=True)
    (root / relpath).write_bytes(data)
    resign(root, signer)


def _write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    members = []
    for path in sorted(root.rglob("*")):
        relpath = path.relative_to(root).as_posix()
        if path.is_file() and relpath not in (MANIFEST, SIGNATURE):
            data = path.read_bytes()
            members.append({"path": relpath, "sha256": hashlib.sha256(data).hexdigest(),
                            "size": len(data)})
    manifest["members"] = sorted(members, key=lambda m: m["path"])
    (root / MANIFEST).write_bytes((json.dumps(manifest, **_JSON) + "\n").encode("utf-8"))
