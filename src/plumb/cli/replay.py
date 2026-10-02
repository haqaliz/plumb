"""Offline replay of a committed gate record through the C4 seam (verify-cli replay).

`replay_record(args)` implements `plumb verify --from-record <dir>`: it reads the
record's own members (`claims.json`, `bindings.json`, `trace.json`, `objects/`,
`paper.pdf` — and, for `--out`, `environment.txt` + `source.json`), re-derives the
verdicts from those committed bytes alone, cross-checks the re-derivation against the
record's `verdicts.json` when it is present, renders through the shared renderer, and
optionally rebuilds the signed bundle. No network, no run, no environment build — the
verdicts are a pure function of the committed evidence, the same guarantee
`tests/gate/test_agrodesign_replay.py` pins.

**The admission gate stays the only door to `Claim`.** `read_record` reads
`claims.json` in either of two forms, decided by the document's key set. The
gate record's curated rule format (`tools/agrodesign_spec.py`) is six fields
per entry — a verbatim value at a span, with the metric and context — and
replay turns each entry into a `Candidate` and admits it again against the
paper through `plumb.extract.admit.admit`, refusing the record if any entry no
longer admits (the record lied about the paper). The serialized C1 form — the
bytes `serialize_claims` writes, `{"claims", "paper_hash"}` — is read back
through `parse_claims`/`readmit` (the same door a C6 bundle's `claims.json`
takes), with the document's `paper_hash` checked against the record's own
paper first.

**The cross-check is the honesty check.** When the record carries `verdicts.json`,
the re-derived verdicts must serialize byte-identically to it; a mismatch means the
record is not what it claims to be and is `RECORD_INVALID`.

**Failures are named.** A missing or malformed member, a trace whose id does not
match, a claim that does not re-admit, a verdict mismatch — all raise `ValueError`,
which the shell renders as `RECORD_INVALID`. `build_bundle` refusals stay
`BUNDLE_REFUSED`. The exit code is the verdict-level contract: 0 iff every claim is
decided, 1 when any is `UNVERIFIED`.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from plumb.bundle import SshSigner, build_bundle, verify_bundle
from plumb.bundle.causes import BundleRefused
from plumb.bundle.verify import paper_text
from plumb.cli.render import render_verdicts
from plumb.extract.admit import NonClaim, admit, readmit
from plumb.extract.candidates import SECTION_OTHER, Candidate
from plumb.extract.hashing import hash_paper
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.serialize import parse_claims
from plumb.intake.checkout import SourceRecord
from plumb.run import parse_trace
from plumb.run.capture import Capture
from plumb.verify import (
    UNVERIFIED,
    Completed,
    VerdictSet,
    load_bindings,
    serialize_verdicts,
    verify_claims,
)

__all__ = ["cross_check", "read_record", "replay_record"]

_PRINCIPAL = "plumb-bundle"

#: The curated claim document's exact per-entry shape (tools/agrodesign_spec.py).
_CURATED_ENTRY_FIELDS = {"text", "metric", "source", "context", "start", "end"}
#: source.json mirrors `SourceRecord`'s fields (src/plumb/intake/checkout.py:49-58).
_SOURCE_FIELDS = {
    "kind", "location", "rev_requested", "rev_resolved", "rev_defaulted", "size_cap_bytes",
}


def replay_record(args) -> int:
    """The replay seam: re-derive from the record, render, and decide the exit code.

    The shell has already rejected the live-mode arguments and checked the signer
    key for `--out`. Raises the engine's named exceptions on failure; returns 0 iff
    every claim is decided.
    """
    record_dir = Path(args.from_record)
    verdicts = _replay(record_dir, args)
    sys.stdout.buffer.write(render_verdicts(verdicts, json=args.json))
    sys.stdout.buffer.flush()
    return 0 if all(v.verdict != UNVERIFIED for v in verdicts.verdicts) else 1


def _replay(record_dir: Path, args) -> VerdictSet:
    claims, bindings_bytes, trace, capture, paper, paper_format = read_record(record_dir)
    bindings = load_bindings(bindings_bytes, [c.id for c in claims])
    verdicts = verify_claims(claims, bindings, Completed(trace, capture))
    cross_check(record_dir, verdicts)
    if args.out is not None:
        _rebuild_bundle(
            record_dir, args, claims, paper, paper_format, bindings_bytes, trace, capture,
        )
    return verdicts


def read_record(record_dir: Path):
    """The record's members, read strictly; missing members are `RECORD_INVALID`."""
    def member(name: str, *, directory: bool = False) -> Path:
        path = record_dir / name
        if path.is_dir() if directory else path.is_file():
            return path
        if directory:
            raise ValueError(f"record {record_dir} is missing its {name}/ directory")
        raise ValueError(f"record {record_dir} is missing {name}")

    claims_path = member("claims.json")
    bindings_path = member("bindings.json")
    trace_path = member("trace.json")
    objects = member("objects", directory=True)
    paper_path = record_dir / "paper.pdf"
    paper_format = "pdf"
    if not paper_path.is_file():
        paper_path = record_dir / "paper.md"
        paper_format = "markdown"
        if not paper_path.is_file():
            raise ValueError(f"record {record_dir} is missing paper.pdf (or paper.md)")

    trace = parse_trace(trace_path.read_bytes())
    capture = Capture(
        store=objects, artifacts=trace.artifacts, stale=trace.stale, causes=trace.causes,
    )
    claims = _read_record_claims(claims_path, record_dir, paper_path, paper_format)
    bindings_bytes = bindings_path.read_bytes()
    return claims, bindings_bytes, trace, capture, paper_path.read_bytes(), paper_format


def _read_record_claims(path: Path, record_dir: Path, paper_path: Path, paper_format: str):
    """The record's claims, in either of the two forms, re-admitted through the gate.

    The document's key set decides which door the claims come through. A
    document with exactly `{"claims"}` is the curated rule form
    (`tools/agrodesign_spec.py`): each entry is a verbatim value at a span,
    admitted again entry by entry against the paper. A document with exactly
    `{"claims", "paper_hash"}` is the serialized C1 form — the bytes
    `serialize_claims` writes — read back through `parse_claims` and
    re-admitted through `readmit`, after the document's `paper_hash` is
    checked against the record's own paper (the same check
    `bundle/verify.py:238` runs): a digest that does not name this paper
    means the claims were not extracted from it, and the record is refused
    whole. Anything else is refused; every refusal is `ValueError`
    (`RECORD_INVALID` in the shell).
    """
    raw = paper_text(paper_path.read_bytes(), paper_format)
    normalized = normalize_text(raw)
    data = path.read_bytes()
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"record {record_dir}: claims.json is not a claim document: {exc!r}"
        ) from None
    if not isinstance(document, dict):
        raise ValueError(f"record {record_dir}: claims.json is not a claim document")
    keys = set(document)
    if keys == {"claims", "paper_hash"}:
        return _admit_serialized_claims(data, record_dir, raw, normalized)
    if keys == {"claims"}:
        return _admit_record_claims(document, record_dir, normalized)
    raise ValueError(
        f"record {record_dir}: claims.json is not a claim document: a claim document "
        "has exactly the fields claims, or claims and paper_hash"
    )


def _admit_serialized_claims(
    data: bytes, record_dir: Path, raw: str, normalized: str
) -> tuple:
    """The record's serialized C1 claims, checked against its own paper.

    `parse_claims` reads back what `serialize_claims` wrote; the document's
    `paper_hash` must equal `hash_paper` of the record's own paper text —
    a mismatch means the claims were not extracted from this paper, and the
    record is refused whole, never partly believed. The records then
    re-admit through the gate (`readmit`), which refuses any record the
    paper no longer grounds, exactly as a C6 bundle's claims re-admit
    (`bundle/verify.py:237-243`).
    """
    try:
        records, paper_hash = parse_claims(data)
    except ValueError as exc:
        raise ValueError(
            f"record {record_dir}: claims.json is not a serialized claim document: "
            f"{exc!r}"
        ) from None
    if hash_paper(raw) != paper_hash:
        raise ValueError(
            f"record {record_dir}: claims.json's paper_hash does not match the "
            "record's paper"
        )
    try:
        return readmit(records, normalized_text=normalized)
    except ValueError as exc:
        raise ValueError(f"record {record_dir}: claims do not re-admit: {exc}") from None


def _admit_record_claims(document: dict, record_dir: Path, normalized: str):
    """The record's curated claims, re-admitted through the gate against the paper.

    Each entry is a value the record says the paper writes at a span. A `Candidate`
    is built from the entry and `admit`ted again — the gate refuses, with a named
    cause, any entry the paper no longer grounds. The paper is the record's own
    `paper.pdf` (or `paper.md`); a record without one cannot re-admit anything and
    is refused earlier, at member reading.
    """
    try:
        entries = document["claims"]
        if not isinstance(entries, list):
            raise ValueError("claims must be a list")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"record {record_dir}: claims.json is not a curated claim document: {exc!r}"
        ) from None

    claims = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != _CURATED_ENTRY_FIELDS:
            raise ValueError(
                f"record {record_dir}: claims.json entry #{index} is not a curated claim"
            )
        candidate = Candidate(
            text=entry["text"],
            span=CharSpan(entry["start"], entry["end"]),
            context=entry["context"],
            section_hint=SECTION_OTHER,
        )
        result = admit(candidate, normalized_text=normalized, metric=entry["metric"])
        if isinstance(result, NonClaim):
            raise ValueError(
                f"record {record_dir}: claim {entry['metric']!r} does not re-admit: "
                f"{result.cause}"
            )
        claims.append(result)
    return tuple(claims)


def cross_check(record_dir: Path, verdicts) -> None:
    """The re-derivation must be byte-identical to the record's committed verdicts."""
    committed = record_dir / "verdicts.json"
    if not committed.is_file():
        return
    if serialize_verdicts(verdicts) != committed.read_bytes():
        raise ValueError(
            f"record {record_dir}: re-derivation differs from committed verdicts.json"
        )


def _rebuild_bundle(record_dir, args, claims, paper, paper_format, bindings, trace, capture) -> Path:
    """The signed bundle from the record's members, then verified under its own key.
    `bindings` here is the record's raw bindings.json bytes, as `build_bundle` takes.
    """
    environment = record_dir / "environment.txt"
    if not environment.is_file():
        raise ValueError(f"record {record_dir} is missing environment.txt (needed for --out)")
    source = _source(record_dir)
    from plumb.cli import DEFAULT_SIGNER_KEY

    key = (
        Path(args.signer_key).expanduser()
        if args.signer_key
        else Path(DEFAULT_SIGNER_KEY).expanduser()
    )
    out = build_bundle(
        Path(args.out),
        claims=claims, paper=paper, paper_format=paper_format, paper_source=None,
        include_paper=not args.no_paper, bindings=bindings, trace=trace, capture=capture,
        environment=environment.read_text(encoding="utf-8"), source=source,
        signer=SshSigner(key, _PRINCIPAL),
    )
    # The builder is also the first verifier; `--no-paper` bundles verify against
    # the record's own paper, which is exactly the verifier-supplied-paper path.
    _self_verify(out, key, paper=None if not args.no_paper else paper)
    return out


def _source(record_dir: Path) -> SourceRecord:
    """The record's `SourceRecord`, from its `source.json` (needed for `--out`)."""
    path = record_dir / "source.json"
    if not path.is_file():
        raise ValueError(f"record {record_dir} is missing source.json (needed for --out)")
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
        if not isinstance(document, dict) or set(document) != _SOURCE_FIELDS:
            raise ValueError("source.json carries exactly the SourceRecord fields")
        return SourceRecord(**document)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"record {record_dir}: source.json is malformed: {exc!r}") from None


def _self_verify(out: Path, key: Path, paper: bytes | None) -> None:
    """The rebuilt bundle must verify under its own key; refuse it if it does not."""
    pub = key.with_name(key.name + ".pub")
    if not pub.is_file():
        raise BundleRefused(f"no public key at {pub} to verify the rebuilt bundle")
    with tempfile.TemporaryDirectory(prefix="plumb-verify-") as tmp:
        allowed = Path(tmp) / "allowed_signers"
        allowed.write_text(f"{_PRINCIPAL} {pub.read_text().strip()}\n", encoding="utf-8")
        report = verify_bundle(out, allowed_signers=allowed, principal=_PRINCIPAL, paper=paper)
    if not report.ok:
        detail = "; ".join(f"{cause}: {text}" for cause, text in report.causes)
        raise BundleRefused(f"the rebuilt bundle does not verify: {detail}")