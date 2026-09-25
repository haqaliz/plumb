"""The verdict set as canonical bytes (M7, S1).

`serialize_verdicts(verdict_set)` renders one JSON document::

    {"run_id": ..., "verdicts": [<one record per claim, by claim_id>],
     "coverage": {"claims", "bound", "by_verdict", "by_cause"}}

The contract is `plumb.run.trace`'s and `plumb.extract.serialize`'s: sorted keys,
no incidental whitespace, UTF-8 without escapes, no NaN, one trailing newline,
pinned by a cross-process byte-identity test. **A `Decimal` leaves as its exact
text** (`str(Decimal("0.870"))` is `"0.870"`), and every field is encoded by
an explicit function that refuses a type it was not told about — a float that
got past the record would be encoded as a binary approximation by `json`
without complaint, so it is caught here instead (risk R2).

**Nothing from the user's machine.** The records carry relpaths, content hashes
and the run id; no absolute path, no wall clock. `coverage` is recomputed from
the records here, never carried alongside them.
"""

from __future__ import annotations

from decimal import Decimal
import json
from typing import Any

from plumb.verify.bindings import CsvCell, JsonPointer, Locator, StdoutRegex
from plumb.verify.verdict import Verdict, VerdictSet

__all__ = ["serialize_verdicts"]

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}


def serialize_verdicts(verdict_set: VerdictSet) -> bytes:
    """The verdict set as one canonical JSON line, UTF-8, newline-terminated."""
    document = {
        "run_id": _optional_str(verdict_set.run_id, "run_id"),
        "verdicts": [_verdict(v) for v in verdict_set.verdicts],
        "coverage": verdict_set.coverage,
    }
    return (json.dumps(document, default=_refuse, **_JSON) + "\n").encode("utf-8")


def _verdict(v: Verdict) -> dict[str, Any]:
    return {
        "claim_id": _str(v.claim_id, "claim_id"),
        "verdict": _str(v.verdict, "verdict"),
        "cause": _optional_str(v.cause, "cause"),
        "review_required": v.review_required,
        "bound": v.bound,
        "reported_text": _str(v.reported_text, "reported_text"),
        "artifact": _optional_str(v.artifact, "artifact"),
        "locator": None if v.locator is None else _locator(v.locator),
        "located_text": _optional_str(v.located_text, "located_text"),
        "sha256": _optional_str(v.sha256, "sha256"),
        "run_id": _optional_str(v.run_id, "run_id"),
        "rederived": _decimal(v.rederived, "rederived"),
        "band": _band(v.band, "band"),
        "tolerance_band": _band(v.tolerance_band, "tolerance_band"),
        "threshold": _decimal(v.threshold, "threshold"),
        "tolerance_threshold": _decimal(v.tolerance_threshold, "tolerance_threshold"),
        "delta": _decimal(v.delta, "delta"),
    }


def _locator(locator: Locator) -> dict[str, Any]:
    if isinstance(locator, JsonPointer):
        return {"kind": "json_pointer", "pointer": _str(locator.pointer, "pointer")}
    if isinstance(locator, StdoutRegex):
        return {"kind": "stdout_regex", "pattern": _str(locator.pattern, "pattern")}
    if isinstance(locator, CsvCell):
        return {
            "kind": "csv_cell",
            "column": _str(locator.column, "column"),
            "row": {_str(k, "row"): _str(val, "row") for k, val in locator.row},
        }
    raise TypeError(f"unknown locator type {type(locator).__name__}")


def _decimal(value: object, field: str) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal:
        raise TypeError(f"{field} must be a Decimal, got {type(value).__name__}: {value!r}")
    return str(value)


def _band(value: object, field: str) -> list[str] | None:
    if value is None:
        return None
    low, high = value  # type: ignore[misc]
    return [_decimal(low, field), _decimal(high, field)]  # type: ignore[list-item]


def _str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string, got {type(value).__name__}")
    return value


def _optional_str(value: object, field: str) -> str | None:
    return None if value is None else _str(value, field)


def _refuse(obj: object) -> Any:
    raise TypeError(f"no canonical encoding for {type(obj).__name__}: {obj!r}")
