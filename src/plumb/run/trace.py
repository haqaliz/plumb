"""The RunTrace record: what actually happened, deterministically (R4).

`build_trace(checkout, result, capture)` folds one run into a `RunTrace` — the
"what ran" record C4 binds against and C6 will bundle — `serialize_trace`
renders it as a single canonical JSON line, and `parse_trace` reads that line
back into the identical record (offline replay starts from the committed bytes,
not from a live run). `parse_trace` recomputes the run id and refuses a record
whose id does not match its own argv, tree hash and artifact hashes.

**No run-side absolute paths.** The run dir, the working copy and the
checkout's location stay on the user's compute; the record carries the
checkout's tree hash, ``cwd = "."`` (the root of the run's working copy of
that tree), and outputs as relpaths plus content hashes. The argv is recorded
verbatim, because it is what ran.

**run_id** is SHA-256 over ``argv + tree hash + sorted locatable artifact
hashes``, in that pinned order: the same program on the same tree producing
the same outputs gets the same id, however many times it runs. mtimes, the
start time, and stderr (diagnostic-only) are provenance, not identity — a
changed warning line must not make a replay look like a different run.

**Canonical bytes.** Sorted keys, no incidental whitespace, UTF-8 without
escapes, no NaN, one trailing newline — the same contract as
`plumb.extract.serialize`, pinned by a cross-process byte-identity test.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from plumb.intake.checkout import Checkout
from plumb.intake.tree import TreeHash
from plumb.run.capture import Artifact, Capture, StaleOutput
from plumb.run.runner import RunFailure, RunResult

__all__ = ["RunTrace", "build_trace", "derive_run_id", "parse_trace", "serialize_trace"]

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}


@dataclass(frozen=True)
class RunTrace:
    """One run: what ran on which tree, how it ended, and what it produced."""

    run_id: str
    tree_hash: TreeHash
    argv: tuple[str, ...]
    entrypoint_source: str
    cwd: str  # always "." — the root of the run's working copy of the tree
    env_policy: str
    timeout_seconds: float
    started_at_ns: int
    exit_code: int | None
    failure: RunFailure | None
    artifacts: tuple[Artifact, ...]
    stale: tuple[StaleOutput, ...]
    causes: tuple[str, ...]


def derive_run_id(
    argv: Iterable[str], tree_hash: TreeHash, artifacts: Iterable[Artifact]
) -> str:
    """SHA-256 over argv + tree hash + sorted locatable artifact hashes."""
    hashes = sorted(a.sha256 for a in artifacts if not a.diagnostic_only)
    parts = [list(argv), tree_hash.scheme, tree_hash.digest, hashes]
    return hashlib.sha256(json.dumps(parts, **_JSON).encode("utf-8")).hexdigest()


def build_trace(checkout: Checkout, result: RunResult, capture: Capture) -> RunTrace:
    """Fold a run and its capture into the deterministic record."""
    return RunTrace(
        run_id=derive_run_id(result.entrypoint.argv, checkout.tree_hash, capture.artifacts),
        tree_hash=checkout.tree_hash,
        argv=result.entrypoint.argv,
        entrypoint_source=result.entrypoint.source,
        cwd=".",
        env_policy=result.env_policy,
        timeout_seconds=result.timeout_seconds,
        started_at_ns=result.started_at_ns,
        exit_code=result.exit_code,
        failure=result.failure,
        artifacts=capture.artifacts,
        stale=capture.stale,
        causes=capture.causes,
    )


def serialize_trace(trace: RunTrace) -> bytes:
    """The trace as one canonical JSON line, UTF-8, newline-terminated."""
    return (json.dumps(_document(trace), **_JSON) + "\n").encode("utf-8")


def _document(trace: RunTrace) -> dict[str, Any]:
    failure = trace.failure
    return {
        "run_id": trace.run_id,
        "tree_hash": {"scheme": trace.tree_hash.scheme, "digest": trace.tree_hash.digest},
        "argv": list(trace.argv),
        "entrypoint_source": trace.entrypoint_source,
        "cwd": trace.cwd,
        "env_policy": trace.env_policy,
        "timeout_seconds": trace.timeout_seconds,
        "started_at_ns": trace.started_at_ns,
        "exit_code": trace.exit_code,
        "failure": None if failure is None else {"cause": failure.cause, "detail": failure.detail},
        "artifacts": [
            {
                "kind": a.kind,
                "relpath": a.relpath,
                "sha256": a.sha256,
                "size": a.size,
                "mtime_ns": a.mtime_ns,
                "diagnostic_only": a.diagnostic_only,
            }
            for a in trace.artifacts
        ],
        "stale": [
            {"relpath": s.relpath, "mtime_ns": s.mtime_ns, "size": s.size, "cause": s.cause}
            for s in trace.stale
        ],
        "causes": list(trace.causes),
    }


def parse_trace(data: bytes) -> RunTrace:
    """The `RunTrace` that `serialize_trace` wrote as `data`; anything else is refused."""
    try:
        doc = json.loads(data.decode("utf-8"))
        failure = doc["failure"]
        trace = RunTrace(
            run_id=_typed(doc["run_id"], str),
            tree_hash=TreeHash(
                scheme=_typed(doc["tree_hash"]["scheme"], str),
                digest=_typed(doc["tree_hash"]["digest"], str),
            ),
            argv=tuple(_typed(arg, str) for arg in doc["argv"]),
            entrypoint_source=_typed(doc["entrypoint_source"], str),
            cwd=_typed(doc["cwd"], str),
            env_policy=_typed(doc["env_policy"], str),
            timeout_seconds=doc["timeout_seconds"],
            started_at_ns=_typed(doc["started_at_ns"], int),
            exit_code=doc["exit_code"],
            failure=None if failure is None else RunFailure(
                cause=_typed(failure["cause"], str), detail=_typed(failure["detail"], str)
            ),
            artifacts=tuple(
                Artifact(
                    kind=_typed(a["kind"], str),
                    relpath=_typed(a["relpath"], str),
                    sha256=_typed(a["sha256"], str),
                    size=_typed(a["size"], int),
                    mtime_ns=a["mtime_ns"],
                    diagnostic_only=_typed(a["diagnostic_only"], bool),
                )
                for a in doc["artifacts"]
            ),
            stale=tuple(
                StaleOutput(
                    relpath=_typed(s["relpath"], str),
                    mtime_ns=_typed(s["mtime_ns"], int),
                    size=_typed(s["size"], int),
                )
                for s in doc["stale"]
            ),
            causes=tuple(_typed(c, str) for c in doc["causes"]),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"not a serialized RunTrace: {exc!r}") from None
    if derive_run_id(trace.argv, trace.tree_hash, trace.artifacts) != trace.run_id:
        raise ValueError("run_id does not match the trace's argv, tree hash and artifacts")
    return trace


def _typed(value: Any, kind: type) -> Any:
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise TypeError(f"expected {kind.__name__}, got {type(value).__name__}")
    return value
