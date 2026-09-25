"""The bindings file: which captured value each claim is checked against (M1).

A binding is user-written in this slice — no model proposes one (`CLAUDE.md` #1).
The file is JSON::

    {"bindings": [
      {"claim_id": "<Claim.id>",
       "artifact": "results.json" | "<stdout>" | "out/table.csv",
       "locator":  {"kind": "json_pointer", "pointer": "/metrics/auc"}
                 | {"kind": "stdout_regex", "pattern": "AUC = (\\S+)"}
                 | {"kind": "csv_cell", "column": "auc", "row": {"model": "A"}},
       "tolerance": {"abs": "0.01"} | {"rel": "0.05"},   # optional
       "scale": "100"}                                    # optional
    ]}

**Two kinds of refusal.** Anything that makes the *file* untrustworthy raises
`BindingInvalid` and nothing is verified: malformed JSON, an unknown or missing
field, a duplicate key, a duplicate `claim_id`, a `claim_id` that names no input
claim (a binding to nothing must not be silently ignored), `<stderr>` as the
artifact (diagnostic-only, never locatable), or a tolerance or scale written as
a JSON *number* — it was parsed as a float by whatever wrote it and its digits
cannot be trusted, so both must be decimal strings. An entry whose locator is
well-formed but unusable — a pointer that is not RFC 6901, a regex that does not
compile or lacks exactly one group, a CSV selector without exactly one key, or a
locator aimed at the wrong artifact kind — only sets `Binding.invalid`, and that
one claim is `UNVERIFIED: BINDING_INVALID`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
import json
import re
from types import MappingProxyType
from typing import Any

from plumb.verify.causes import BindingInvalid
from plumb.verify.numbers import Tolerance, strict_decimal

__all__ = ["Binding", "CsvCell", "JsonPointer", "StdoutRegex", "load_bindings"]

STDOUT = "<stdout>"
STDERR = "<stderr>"


@dataclass(frozen=True, slots=True)
class JsonPointer:
    """An RFC 6901 pointer into a captured ``.json`` artifact."""

    pointer: str


@dataclass(frozen=True, slots=True)
class StdoutRegex:
    """A regex with exactly one capture group, matched over the run's stdout."""

    pattern: str


@dataclass(frozen=True, slots=True)
class CsvCell:
    """The cell in `column` of the one row whose key column holds the key value."""

    column: str
    row: tuple[tuple[str, str], ...]  # exactly one (key column, key value) when valid


Locator = JsonPointer | StdoutRegex | CsvCell


@dataclass(frozen=True, slots=True)
class Binding:
    """One claim's binding. `invalid` holds why the locator is unusable, if it is."""

    claim_id: str
    artifact: str
    locator: Locator
    tolerance: Tolerance | None
    scale: Decimal | None
    invalid: str | None


_ENTRY_FIELDS = {"claim_id", "artifact", "locator", "tolerance", "scale"}
_LOCATOR_FIELDS = {
    "json_pointer": {"kind", "pointer"},
    "stdout_regex": {"kind", "pattern"},
    "csv_cell": {"kind", "column", "row"},
}
_POINTER = re.compile(r"(?:/(?:[^~/]|~[01])*)*")


def load_bindings(raw: bytes, claim_ids: Iterable[str]) -> Mapping[str, Binding]:
    """Parse and validate a bindings file against the claim ids it may bind."""
    known = list(claim_ids)
    if len(set(known)) != len(known):
        raise BindingInvalid("the claim set carries duplicate claim ids")
    document = _parse(raw)
    if not isinstance(document, dict) or set(document) != {"bindings"}:
        raise BindingInvalid('the file must be an object with exactly one field, "bindings"')
    entries = document["bindings"]
    if not isinstance(entries, list):
        raise BindingInvalid('"bindings" must be a list')

    bindings: dict[str, Binding] = {}
    for index, item in enumerate(entries):
        binding = _binding(index, item, set(known))
        if binding.claim_id in bindings:
            raise BindingInvalid(f"claim {binding.claim_id} is bound more than once")
        bindings[binding.claim_id] = binding
    return MappingProxyType(dict(sorted(bindings.items())))


def _parse(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in items]
        if len(set(keys)) != len(keys):
            raise BindingInvalid(f"duplicate key in bindings file: {sorted(keys)}")
        return dict(items)

    def constant(name: str) -> Any:
        raise BindingInvalid(f"{name} is not a value a bindings file may hold")

    try:
        return json.loads(
            raw.decode("utf-8"),
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=constant,
            object_pairs_hook=pairs,
        )
    except UnicodeDecodeError as exc:
        raise BindingInvalid(f"bindings file is not UTF-8: {exc}") from None
    except json.JSONDecodeError as exc:
        raise BindingInvalid(f"bindings file is not JSON: {exc}") from None


def _binding(index: int, item: Any, known: set[str]) -> Binding:
    where = f"binding #{index}"
    if not isinstance(item, dict):
        raise BindingInvalid(f"{where} is not an object")
    claim_id = item.get("claim_id")
    if not isinstance(claim_id, str):
        raise BindingInvalid(f"{where} has no string claim_id")
    where = f"binding for claim {claim_id}"
    if claim_id not in known:
        raise BindingInvalid(f"{where}: claim {claim_id} is not among the claims")
    unknown = set(item) - _ENTRY_FIELDS
    if unknown:
        raise BindingInvalid(f"{where}: unknown fields {sorted(unknown)}")
    artifact = item.get("artifact")
    if not isinstance(artifact, str):
        raise BindingInvalid(f"{where}: artifact must be a string")
    if artifact == STDERR:
        raise BindingInvalid(f"{where}: stderr is diagnostic-only and is never bound")

    locator, invalid = _locator(where, item.get("locator"))
    mismatch = _kind_mismatch(artifact, locator)
    return Binding(
        claim_id=claim_id,
        artifact=artifact,
        locator=locator,
        tolerance=_tolerance(where, item.get("tolerance")),
        scale=_scale(where, item.get("scale")),
        invalid=invalid or mismatch,
    )


def _locator(where: str, spec: Any) -> tuple[Locator, str | None]:
    """The locator and, if it is unusable, why. Schema errors raise."""
    if not isinstance(spec, dict) or spec.get("kind") not in _LOCATOR_FIELDS:
        raise BindingInvalid(f"{where}: locator must be an object with a known kind")
    kind = spec["kind"]
    if set(spec) != _LOCATOR_FIELDS[kind]:
        raise BindingInvalid(
            f"{where}: a {kind} locator has exactly the fields {sorted(_LOCATOR_FIELDS[kind])}"
        )

    if kind == "json_pointer":
        pointer = _string(where, spec, "pointer")
        ok = _POINTER.fullmatch(pointer) is not None
        return JsonPointer(pointer), None if ok else f"not an RFC 6901 pointer: {pointer!r}"

    if kind == "stdout_regex":
        pattern = _string(where, spec, "pattern")
        try:
            groups = re.compile(pattern).groups
        except re.error as exc:
            return StdoutRegex(pattern), f"regex does not compile: {exc}"
        if groups != 1:
            return StdoutRegex(pattern), f"regex must have exactly one group, has {groups}"
        return StdoutRegex(pattern), None

    column = _string(where, spec, "column")
    row = spec["row"]
    if not isinstance(row, dict) or not all(isinstance(v, str) for v in row.values()):
        raise BindingInvalid(f"{where}: csv row must map column names to strings")
    cell = CsvCell(column, tuple(sorted(row.items())))
    if len(row) != 1:
        return cell, f"csv row selector must have exactly one key, has {len(row)}"
    return cell, None


def _kind_mismatch(artifact: str, locator: Locator) -> str | None:
    wanted = {
        JsonPointer: lambda a: a.lower().endswith(".json"),
        StdoutRegex: lambda a: a == STDOUT,
        CsvCell: lambda a: a.lower().endswith(".csv"),
    }[type(locator)]
    if wanted(artifact):
        return None
    return f"a {type(locator).__name__} locator cannot read {artifact!r}"


def _string(where: str, spec: dict[str, Any], field: str) -> str:
    value = spec[field]
    if not isinstance(value, str):
        raise BindingInvalid(f"{where}: locator {field} must be a string")
    return value


def _decimal_string(where: str, name: str, value: Any) -> Decimal:
    if not isinstance(value, str):
        raise BindingInvalid(
            f"{where}: {name} must be a decimal string (a JSON number went through a float)"
        )
    parsed = strict_decimal(value)
    if parsed is None:
        raise BindingInvalid(f"{where}: {name} {value!r} is not a plain decimal")
    return parsed


def _tolerance(where: str, spec: Any) -> Tolerance | None:
    if spec is None:
        return None
    if not isinstance(spec, dict) or len(spec) != 1 or next(iter(spec)) not in ("abs", "rel"):
        raise BindingInvalid(f'{where}: tolerance must be {{"abs": ...}} or {{"rel": ...}}')
    (kind, value), = spec.items()
    parsed = _decimal_string(where, "tolerance", value)
    if parsed < 0:
        raise BindingInvalid(f"{where}: tolerance must be non-negative")
    return Tolerance(kind, parsed)


def _scale(where: str, value: Any) -> Decimal | None:
    if value is None:
        return None
    parsed = _decimal_string(where, "scale", value)
    if parsed <= 0:
        raise BindingInvalid(f"{where}: scale must be positive")
    return parsed
