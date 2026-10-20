"""BYOK binding proposer (issue #24): a model may propose, only execution may agree.

A proposer is a **user-supplied command** (`--proposer CMD`). Plumb writes a JSON request to its
stdin — the claims (id, metric, reported text, units) and the run's locatable artifact paths —
and reads a bindings-shaped document from its stdout. No SDK, no network code and no model name
lives in this repo; the user wires their own model, on their own compute, with their own key.

**Every proposal is re-grounded before it is kept.** A proposal is dropped unless its claim id is
one of the paper's, its artifact is one the run actually wrote, its locator parses under the same
rules a hand-written bindings file must satisfy, and the locator resolves to exactly one fresh
value in the capture. The accepted proposals become a normal bindings document, which then goes
through `load_bindings` and `verify_claims` like any other — so a proposal can never assign a
verdict, never make a claim `REPRODUCED`, and never make one `DIVERGED`.

The accepted bindings are what the bundle carries, so a proposed verification replays without the
model: the proposal is provenance, the run is the evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import shlex
import subprocess

from plumb.verify.bindings import BindingInvalid, load_bindings
from plumb.verify.locate import Located, locate

__all__ = [
    "MODEL_ONLY_SIGNAL",
    "PROPOSER_FAILED",
    "PROPOSER_UNGROUNDED",
    "ProposalRefused",
    "propose_bindings",
    "request_document",
]

#: The proposal is malformed, names an unknown claim, or an artifact the run did not write.
PROPOSER_UNGROUNDED = "PROPOSER_UNGROUNDED"
#: The proposed locator resolves to no unique fresh value: a model signal with no evidence.
MODEL_ONLY_SIGNAL = "MODEL_ONLY_SIGNAL"
#: The proposer command could not run, timed out, or wrote something that is not a bindings doc.
PROPOSER_FAILED = "PROPOSER_FAILED"

_JSON = {"sort_keys": True, "ensure_ascii": False, "separators": (",", ":")}

#: A proposer gets the same wall clock as a run's default; a hung model is not a hang.
_TIMEOUT_SECONDS = 300


class ProposalRefused(RuntimeError):
    """The proposer itself failed; the claims' verdicts are untouched."""

    def __init__(self, message: str, cause: str = PROPOSER_FAILED) -> None:
        super().__init__(message)
        self.cause = cause


@dataclass(frozen=True)
class Refusal:
    """One dropped proposal, with its named cause — never a silent drop."""

    cause: str
    detail: str


def request_document(claims, capture) -> bytes:
    """What the proposer is shown: claims and artifact paths, never paper bytes or outputs."""
    return (
        json.dumps(
            {
                "claims": [
                    {
                        "id": c.id, "metric": c.metric,
                        "reported": c.reported_value.text, "units": c.units,
                    }
                    for c in claims
                ],
                "artifacts": [
                    {"relpath": a.relpath, "kind": a.kind} for a in capture.locatable
                ],
            },
            **_JSON,
        )
        + "\n"
    ).encode("utf-8")


def propose_bindings(
    command: str, claims, capture, *, timeout_seconds: float = _TIMEOUT_SECONDS
) -> tuple[bytes, tuple[Refusal, ...]]:
    """Run the proposer, re-ground every proposal; returns `(accepted bindings bytes, refusals)`."""
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ProposalRefused(f"the proposer command does not parse: {exc}") from exc
    if not argv:
        raise ProposalRefused("the proposer command is empty")
    try:
        result = subprocess.run(
            argv, input=request_document(claims, capture), capture_output=True,
            timeout=timeout_seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProposalRefused(f"the proposer did not run: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ProposalRefused(
            f"the proposer exited {result.returncode}"
            + (f": {stderr[0]}" if stderr else "")
        )
    return ground(result.stdout, claims, capture)


def ground(data: bytes, claims, capture) -> tuple[bytes, tuple[Refusal, ...]]:
    """Keep only the proposals that point at a real, fresh, unique value in the run."""
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProposalRefused(f"the proposer did not write JSON: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"bindings"}:
        raise ProposalRefused('the proposer must write an object with exactly one field, "bindings"')
    if not isinstance(document["bindings"], list):
        raise ProposalRefused('"bindings" must be a list')

    known = {c.id for c in claims}
    artifacts = {a.relpath for a in capture.locatable}
    accepted: list[dict] = []
    refusals: list[Refusal] = []
    for index, entry in enumerate(document["bindings"]):
        reduced = _shape(entry, index, refusals)
        if reduced is None:
            continue
        if reduced["claim_id"] not in known:
            refusals.append(Refusal(
                PROPOSER_UNGROUNDED, f"proposal {index} names an unknown claim {reduced['claim_id']!r}"
            ))
            continue
        if any(item["claim_id"] == reduced["claim_id"] for item in accepted):
            refusals.append(Refusal(
                PROPOSER_UNGROUNDED,
                f"proposal {index} repeats claim {reduced['claim_id']!r}; the first grounding wins",
            ))
            continue
        if reduced["artifact"] not in artifacts:
            refusals.append(Refusal(
                PROPOSER_UNGROUNDED,
                f"proposal {index} names {reduced['artifact']!r}, which the run did not write",
            ))
            continue
        try:
            binding = load_bindings(
                json.dumps({"bindings": [reduced]}, **_JSON).encode("utf-8"),
                [reduced["claim_id"]],
            )[reduced["claim_id"]]
        except BindingInvalid as exc:
            refusals.append(Refusal(PROPOSER_UNGROUNDED, f"proposal {index} is not a valid binding: {exc}"))
            continue
        found = locate(binding, capture)
        if not isinstance(found, Located):
            refusals.append(Refusal(
                MODEL_ONLY_SIGNAL,
                f"proposal {index} points at no unique fresh value: {found.cause}",
            ))
            continue
        accepted.append(reduced)

    accepted.sort(key=lambda item: item["claim_id"])
    return json.dumps({"bindings": accepted}, **_JSON).encode("utf-8"), tuple(refusals)


def _shape(entry, index: int, refusals: list[Refusal]) -> dict | None:
    """A proposal's fields only: unknown keys and wrong types are refused, not coerced."""
    if not isinstance(entry, dict):
        refusals.append(Refusal(PROPOSER_UNGROUNDED, f"proposal {index} is not an object"))
        return None
    allowed = {"claim_id", "artifact", "locator", "tolerance", "scale", "float_repr"}
    extra = set(entry) - allowed
    if extra:
        refusals.append(Refusal(PROPOSER_UNGROUNDED, f"proposal {index} has unknown fields {sorted(extra)}"))
        return None
    if not isinstance(entry.get("claim_id"), str) or not isinstance(entry.get("artifact"), str):
        refusals.append(Refusal(PROPOSER_UNGROUNDED, f"proposal {index} needs string claim_id and artifact"))
        return None
    if not isinstance(entry.get("locator"), dict):
        refusals.append(Refusal(PROPOSER_UNGROUNDED, f"proposal {index} needs a locator object"))
        return None
    return {key: entry[key] for key in allowed if key in entry}
