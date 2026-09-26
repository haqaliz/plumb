"""Locate a bound value in what the run actually produced (M2).

`locate(binding, capture)` → `Located` (the verbatim text, its strict `Decimal`,
its written half-unit, and the artifact's relpath and SHA-256) or `Unlocated`
(a named cause). It compares nothing; `compare` decides.

**The order of checks is the guarantee.**

1. An invalid binding entry is `BINDING_INVALID` before anything is read.
2. A target that is a `StaleOutput` is `STALE_ARTIFACT`, and its bytes are never
   read — there are none in the store to read (`CLAUDE.md` #5). This check comes
   before the lookup, and lives in `_stale_target` so the false-`DIVERGED` guard
   can prove, by patching it out, that the suite notices its absence.
3. A target the run did not write (or stderr, which is never locatable) is
   `NO_BINDING`.
4. Only then are bytes read, and only through `Capture.read`, which re-checks the
   hash. Its integrity `ValueError` is deliberately **not** caught: a tampered
   store is a harness failure, not a fact about the claim, and must never be
   folded into a verdict.

**Exactly one value, or a cause.** Zero matches is `NO_BINDING`; more than one
is `AMBIGUOUS_BINDING` — Plumb does not pick. For JSON that includes a
duplicated object key *anywhere* in the document: the standard parser cannot
say whether the duplicate sits on the pointer's path, so the conservative
reading is that the document is ambiguous.

**Written precision** is the located text's last digit, unless the binding declares
`float_repr` — then the half-unit is 0 (see `plumb.verify.bindings`).

**No float.** A JSON number reaches `strict_decimal` as the literal text the run
wrote, so `0.870` keeps its three places and nothing passes through a binary
approximation. NaN and Infinity are refused, as is any leaf that is not a number
or a plain decimal string.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
import io
import json
import re
from typing import Any

from plumb.run.capture import Artifact, Capture
from plumb.verify.bindings import Binding, CsvCell, JsonPointer, StdoutRegex
from plumb.verify.causes import (
    AMBIGUOUS_BINDING,
    BINDING_INVALID,
    NO_BINDING,
    STALE_ARTIFACT,
    UNPARSEABLE_VALUE,
)
from plumb.verify.numbers import half_unit, strict_decimal

__all__ = ["Located", "Unlocated", "locate"]


@dataclass(frozen=True, slots=True)
class Located:
    """One value the run wrote, exactly as it wrote it."""

    text: str
    value: Decimal
    half_unit: Decimal
    relpath: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Unlocated:
    """Why no single value could be located."""

    cause: str
    detail: str


def locate(binding: Binding, capture: Capture) -> Located | Unlocated:
    """The one value `binding` points at in `capture`, or the named reason there isn't one."""
    if binding.invalid is not None:
        return Unlocated(BINDING_INVALID, binding.invalid)
    if _stale_target(binding, capture):
        return Unlocated(STALE_ARTIFACT, f"{binding.artifact} predates the run")
    artifact = {a.relpath: a for a in capture.locatable}.get(binding.artifact)
    if artifact is None:
        return Unlocated(NO_BINDING, f"the run did not write {binding.artifact}")

    data = capture.read(artifact)
    locator = binding.locator
    if isinstance(locator, JsonPointer):
        found = _json(data, locator.pointer)
    elif isinstance(locator, StdoutRegex):
        found = _stdout(data, locator.pattern)
    else:
        found = _csv(data, locator)
    if isinstance(found, Unlocated):
        return found
    return _number(found, artifact, exact=binding.float_repr)


def _stale_target(binding: Binding, capture: Capture) -> bool:
    return binding.artifact in {s.relpath for s in capture.stale}


def _number(text: str, artifact: Artifact, *, exact: bool) -> Located | Unlocated:
    value = strict_decimal(text)
    if value is None:
        return Unlocated(UNPARSEABLE_VALUE, f"{text!r} in {artifact.relpath} is not a number")
    # A shortest round-trip float repr is the program's exact double, not a rounding.
    precision = Decimal(0) if exact else half_unit(value)
    return Located(text, value, precision, artifact.relpath, artifact.sha256)


# --------------------------------------------------------------------------------
# JSON pointer
# --------------------------------------------------------------------------------


class _Literal(str):
    """A JSON number, kept as the literal text the run wrote."""


class _Duplicate(Exception):
    pass


class _Constant(Exception):
    pass


_INDEX = re.compile(r"0|[1-9][0-9]*")


def _json(data: bytes, pointer: str) -> str | Unlocated:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in items]
        if len(set(keys)) != len(keys):
            raise _Duplicate(sorted(k for k in set(keys) if keys.count(k) > 1))
        return dict(items)

    def constant(name: str) -> Any:
        raise _Constant(name)

    try:
        node = json.loads(
            data.decode("utf-8"),
            parse_float=_Literal,
            parse_int=_Literal,
            parse_constant=constant,
            object_pairs_hook=pairs,
        )
    except _Duplicate as exc:
        return Unlocated(AMBIGUOUS_BINDING, f"duplicate JSON keys {exc}")
    except _Constant as exc:
        return Unlocated(UNPARSEABLE_VALUE, f"JSON holds {exc}, which is not a number")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return Unlocated(UNPARSEABLE_VALUE, f"not a JSON document: {exc}")

    for token in pointer.split("/")[1:]:
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and key in node:
            node = node[key]
        elif isinstance(node, list) and _INDEX.fullmatch(key) and int(key) < len(node):
            node = node[int(key)]
        else:
            return Unlocated(NO_BINDING, f"pointer {pointer!r} resolves to nothing")

    if isinstance(node, str):  # a _Literal number, or a string that may hold one
        return str(node)
    return Unlocated(UNPARSEABLE_VALUE, f"pointer {pointer!r} holds {type(node).__name__}")


# --------------------------------------------------------------------------------
# stdout regex
# --------------------------------------------------------------------------------


def _stdout(data: bytes, pattern: str) -> str | Unlocated:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return Unlocated(UNPARSEABLE_VALUE, f"stdout is not UTF-8: {exc}")
    matches = list(re.finditer(pattern, text))
    if len(matches) > 1:
        return Unlocated(AMBIGUOUS_BINDING, f"{pattern!r} matched stdout {len(matches)} times")
    if not matches or matches[0].group(1) is None:
        return Unlocated(NO_BINDING, f"{pattern!r} located nothing in stdout")
    return matches[0].group(1)


# --------------------------------------------------------------------------------
# CSV cell
# --------------------------------------------------------------------------------


def _csv(data: bytes, locator: CsvCell) -> str | Unlocated:
    try:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"), newline="")))
    except (UnicodeDecodeError, csv.Error) as exc:
        return Unlocated(UNPARSEABLE_VALUE, f"not a readable CSV: {exc}")
    if not rows:
        return Unlocated(NO_BINDING, "the CSV is empty")

    header = [name.strip() for name in rows[0]]
    (key_column, key_value), = locator.row
    for name in (locator.column, key_column):
        count = header.count(name)
        if count == 0:
            return Unlocated(NO_BINDING, f"no column {name!r} in the CSV header")
        if count > 1:
            return Unlocated(AMBIGUOUS_BINDING, f"column {name!r} appears {count} times")

    key_at, column_at = header.index(key_column), header.index(locator.column)
    matching = [
        row for row in rows[1:] if len(row) > key_at and row[key_at].strip() == key_value
    ]
    if len(matching) > 1:
        return Unlocated(AMBIGUOUS_BINDING, f"{len(matching)} rows have {key_column}={key_value}")
    if not matching or len(matching[0]) <= column_at:
        return Unlocated(NO_BINDING, f"no {locator.column} cell for {key_column}={key_value}")
    return matching[0][column_at]
