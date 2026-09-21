"""The serialized form: the same claims in, the same bytes out, forever.

This module turns a set of `Claim` records plus the `PaperHash` naming the paper they
came from into one JSON document. That document is the contract C6 bundles and a third
party replays, so its bytes — not its meaning — are what must be stable.

Four decisions carry the weight.

**It returns `bytes`, not `str`.** "Byte-identical" is only assertable on bytes; a
`str` leaves the encoding unpinned, and the encoding is half of what makes two outputs
the same output.

**Every JSON option is pinned on `SERIALIZATION`, not at the call site.** `sort_keys`,
`ensure_ascii`, `separators`, `indent` and the trailing newline each have a default
that would have been fine, and each of them changes the bytes. Written out in one
place, the contract is readable; inferred from a call site, it is a guess.

**A `Decimal` leaves as its verbatim text, never through a float.** `Decimal` is not
JSON-serializable, and the reflex repair — a `default=` that reaches for the nearest
binary approximation — would reintroduce risk **R2** (`docs/ROADMAP.md:57`) at the last
possible moment, after the whole record layer spent its effort keeping it out. So the
encoder here is a registry of known types that **refuses** anything it was not told
about. There is no fallback, because a fallback that "just works" is how a float gets
in. A new value or location variant must be registered here, and the test suite fails
until it is.

**Nothing reads ambient state** (decision D1 of the aspect plan). No clock, no working
directory, no environment, no randomness, no locale-sensitive call. Determinism comes
from not having sources of nondeterminism, not from scrubbing them afterwards — a
timestamp stripped from the output is still a timestamp that was generated.

This module emits no verdicts. It writes down what was extracted, nothing more.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
import json
from typing import Any, Callable

from plumb.extract.claim import Claim
from plumb.extract.hashing import PaperHash
from plumb.extract.location import CharSpan, Location
from plumb.extract.ordering import location_sort_key, optional_sort_key
from plumb.extract.value import (
    Approximate,
    Bound,
    ClaimValue,
    Interval,
    Point,
    PlusMinus,
    Range,
)

__all__ = ["SERIALIZATION", "serialize_claims"]


# --------------------------------------------------------------------------------
# The pinned options
# --------------------------------------------------------------------------------


def _refuse_unknown(obj: object) -> Any:
    """The `default=` hook, which exists only to refuse.

    `json.dumps` calls this for any object it cannot encode. The useful thing to do
    here would be to convert — and that is exactly the hole this module closes, since
    the conversion a `Decimal` invites is the lossy one. Every value reaching the
    encoder has already passed through `_encode_claim`, so arriving here means a type
    slipped past the registry: report it rather than repair it.
    """
    raise TypeError(
        f"refusing to serialize an unregistered type: {type(obj).__name__}: {obj!r}. "
        "Register it in serialize.py rather than adding a coercion."
    )


@dataclass(frozen=True, slots=True)
class _Serialization:
    """The serialized form's formatting contract, stated rather than implied.

    Each field is a `json.dumps` argument that has a perfectly reasonable default and
    a different one here, plus the two things `json.dumps` does not decide at all: the
    encoding the document is emitted in, and the terminator.

    `default=` is deliberately *not* a field. It is always `_refuse_unknown`: a
    configurable fallback is precisely the hole that lets a `Decimal` leave as a
    binary approximation, so it is not offered as a knob.
    """

    #: Key order must not depend on dict insertion order, which depends on the code
    #: path that built the dict.
    sort_keys: bool = True
    #: Keep é, – and µ as themselves. `\\uXXXX` escapes would be stable too, but the
    #: document is read by humans and diffed by reviewers.
    ensure_ascii: bool = False
    #: No incidental whitespace; the default `(", ", ": ")` adds bytes that carry no
    #: information.
    separators: tuple[str, str] = (",", ":")
    #: One line. Pinned explicitly because it is already the default and a reader
    #: should not have to know that.
    indent: int | str | None = None
    #: `NaN` and `Infinity` are not JSON, and no finite float should reach the encoder
    #: either — this makes the impossible case loud rather than silently non-standard.
    allow_nan: bool = False
    #: The bytes the document is emitted in. Half of "byte-identical".
    encoding: str = "utf-8"
    #: One, always — so the document is a well-formed line in a file and appending
    #: never joins two documents.
    trailing_newline: str = "\n"

    @property
    def json_options(self) -> dict[str, Any]:
        """The exact keyword arguments handed to `json.dumps`."""
        return {
            "sort_keys": self.sort_keys,
            "ensure_ascii": self.ensure_ascii,
            "separators": self.separators,
            "indent": self.indent,
            "allow_nan": self.allow_nan,
            "default": _refuse_unknown,
        }


#: The one place the serialized form's formatting is decided.
SERIALIZATION = _Serialization()


# --------------------------------------------------------------------------------
# The encoders — a closed registry, with no fallback
# --------------------------------------------------------------------------------


def _decimal(value: object, field: str) -> str:
    """A `Decimal` as its own exact text.

    `str(Decimal("0.870"))` is `"0.870"`: the coefficient and exponent the value was
    built with, round-tripping through `Decimal(...)` unchanged. The significant
    figures a paper chose survive here, which numeric equality does not preserve —
    `Decimal("0.870") == Decimal("0.87")` is `True`.
    """
    if not isinstance(value, Decimal):
        raise TypeError(
            f"expected a Decimal for {field}, got {type(value).__name__}: {value!r}"
        )
    return str(value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"expected a string for {field}, got {type(value).__name__}: {value!r}"
        )
    return value


def _optional_string(value: object, field: str) -> str | None:
    """`None` stays `None`: it is a fact the caller stated, not an absent string.

    A dimensionless metric (`units=None`) and a caller who wrote `units=""` are
    different records — aspect 1's `id` already distinguishes them — so the serialized
    form must not fuse them into one spelling.
    """
    return None if value is None else _string(value, field)


_Encoder = Callable[[object, str], Any]

# ORDER IS NOT THE CONTRACT HERE — `sort_keys=True` decides key order — but the *tags*
# are. A tag is what tells `Interval` apart from `Range` once both are a text with a
# low and a high, so the strings below are pinned literals rather than derived from
# class names: renaming a class must not silently change every document ever written.
# `ClaimValue` itself is absent on purpose; it is not constructible.
_VALUE_VARIANTS: Mapping[type, tuple[str, tuple[tuple[str, _Encoder], ...]]] = {
    Point: ("point", (("value", _decimal),)),
    Bound: ("bound", (("op", _string), ("magnitude", _decimal))),
    PlusMinus: ("plus_minus", (("center", _decimal), ("margin", _decimal))),
    Interval: ("interval", (("low", _decimal), ("high", _decimal))),
    Range: ("range", (("low", _decimal), ("high", _decimal))),
    Approximate: ("approximate", (("value", _decimal),)),
}


def _encode_value(value: ClaimValue) -> dict[str, Any]:
    """One `ClaimValue` variant, tagged, with its components as exact text."""
    # Exact type, never `isinstance`: a subclass of `Point` encoded as a `Point` would
    # be written out with its own fields silently dropped.
    variant = _VALUE_VARIANTS.get(type(value))
    if variant is None:
        raise TypeError(
            f"refusing to serialize an unregistered ClaimValue variant: "
            f"{type(value).__name__}: {value!r}. Register it in serialize.py — a "
            "variant that falls through would be written out as some other variant."
        )
    tag, fields = variant
    encoded: dict[str, Any] = {
        "kind": tag,
        "text": _string(value.text, "ClaimValue.text"),
    }
    for name, encode in fields:
        encoded[name] = encode(getattr(value, name), f"{type(value).__name__}.{name}")
    return encoded


def _offset(value: object, field: str) -> int:
    # `bool` is an `int` subclass; `CharSpan` already rejects it, and so does this, so
    # neither layer depends on the other for it.
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(
            f"expected an int character offset for {field}, got "
            f"{type(value).__name__}: {value!r}"
        )
    return value


def _encode_location(location: Location) -> dict[str, Any]:
    """The one registered `Location` variant.

    `CharSpan.kind` is reused rather than re-spelled: `location.py` already enforces
    that every variant carries a `kind` tag, and a second literal here could only ever
    drift from it. A future variant (`PageBox`) must extend this function *and*
    `location_sort_key` — the sort key needs an ordering for it, and there is no
    honest default for a variant this module has never seen.
    """
    if type(location) is not CharSpan:
        raise TypeError(
            f"refusing to serialize an unregistered Location variant: "
            f"{type(location).__name__}: {location!r}. Register it in serialize.py, "
            "including its place in the sort key."
        )
    return {
        "kind": CharSpan.kind,
        "start": _offset(location.start, "CharSpan.start"),
        "end": _offset(location.end, "CharSpan.end"),
    }


def _encode_claim(claim: Claim) -> dict[str, Any]:
    """One `Claim`, every field carried, nothing derived beyond what the record holds."""
    return {
        "id": _string(claim.id, "Claim.id"),
        "metric": _string(claim.metric, "Claim.metric"),
        "units": _optional_string(claim.units, "Claim.units"),
        "reported_value": _encode_value(claim.reported_value),
        "location": _encode_location(claim.location),
        "artifact_hint": _optional_string(claim.artifact_hint, "Claim.artifact_hint"),
        "tolerance_hint": _optional_string(claim.tolerance_hint, "Claim.tolerance_hint"),
    }


# --------------------------------------------------------------------------------
# Ordering — the shared keys live in `ordering.py`. What remains here is the
# serializer's own key, which ends in the canonical encoding only it can produce.
# --------------------------------------------------------------------------------


def _order_key(claim: Claim, canonical: str) -> tuple[Any, ...]:
    """The total key claims are written in (decision D2, corrected to be total).

    D2 states the key as `(reported_value.text, metric, units or "", location.start,
    location.end)`. Two of those five are wrong, in ways that leave the key partial —
    and a partial key falls back to input order, since `sorted()` is stable but its
    input may not be:

    - `units or ""` erases the `None`/`""` distinction (see `optional_sort_key`).
    - `location.start` / `location.end` are `CharSpan` attributes, not `Location` ones;
      the union exists so `PageBox` can join it (see `location_sort_key`).

    Both come from `plumb.extract.ordering`, which `dedup.py` imports too: two modules
    ordering the same records differently would be its own bug, and a single
    implementation is what rules it out rather than a test comparing two copies. The
    hint components use the same helper the shared `member_sort_key` does.

    The claim's own canonical encoding is the last component and the backstop. Even
    with every field above accounted for, two records can agree on all of them and
    still differ — a hand-built `Bound` whose `text` happens to read `"0.87"` against a
    parsed `Point`, say. Ending on the encoding makes the key total by construction:
    claims tie only when they serialize to identical bytes, and then their order cannot
    be observed.
    """
    return (
        claim.reported_value.text,
        claim.metric,
        optional_sort_key(claim.units),
        location_sort_key(claim.location),
        optional_sort_key(claim.artifact_hint),
        optional_sort_key(claim.tolerance_hint),
        canonical,
    )


# --------------------------------------------------------------------------------
# The public function
# --------------------------------------------------------------------------------


def serialize_claims(claims: Iterable[Claim], *, paper_hash: PaperHash) -> bytes:
    """Serialize `claims` under `paper_hash` to the pinned byte form.

    `paper_hash` is the `PaperHash` **record**, never a bare hex string: a digest that
    arrived from elsewhere and got stamped with an algorithm name by this function
    would be *mislabeled*, which is worse than unlabeled — a replayer is told how to
    verify it and the instruction is wrong. The algorithm travels with the digest it
    belongs to, and is not a parameter of this function: making it one would add a
    second input and turn "identical input → identical bytes" into "identical input
    *and callers who agree* → identical bytes".

    There is no schema or tool version in the output. That would change the bytes for
    unchanged content whenever the stamp moved, and version and provenance belong to
    C6's bundle envelope. The algorithm name is not such a stamp: it can only ever
    accompany a digest that has already changed.

    Raises `TypeError` for anything unregistered, and never falls back to a coercion.
    """
    if not isinstance(paper_hash, PaperHash):
        raise TypeError(
            "serialize_claims takes the PaperHash record, not a bare digest; got "
            f"{type(paper_hash).__name__}: {paper_hash!r}"
        )

    options = SERIALIZATION.json_options

    rows: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for claim in claims:
        if not isinstance(claim, Claim):
            raise TypeError(
                f"serialize_claims takes Claim records, got "
                f"{type(claim).__name__}: {claim!r}"
            )
        # Encoded once. The same encoding is what gets written and what breaks a tie,
        # so the order and the bytes can never be derived from different renderings.
        body = _encode_claim(claim)
        rows.append((_order_key(claim, json.dumps(body, **options)), body))

    rows.sort(key=lambda row: row[0])

    document = {
        "claims": [body for _, body in rows],
        "paper_hash": {
            "algorithm": paper_hash.algorithm,
            "digest": paper_hash.digest,
        },
    }
    text = json.dumps(document, **options) + SERIALIZATION.trailing_newline
    return text.encode(SERIALIZATION.encoding)
