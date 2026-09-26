"""`parse_claims` + `readmit`: a serialized claim document read back (signed-bundle B1).

C6 verifies a bundle from its bytes alone. Reading bytes must not become a second door to
`Claim` (only the admission gate constructs one — `test_admit.py`), so `parse_claims` returns
plain records and `readmit` turns them into claims by admitting each one again against the
paper text. Pinned: the round trip is the identity for every value variant; a record whose id
or value does not match what the paper says at its span is refused; anything else is refused.
"""

from __future__ import annotations

from decimal import Decimal
import json

import pytest

from plumb.extract.admit import readmit
from plumb.extract.claim import Claim
from plumb.extract.hashing import hash_paper
from plumb.extract.location import CharSpan, normalize_text
from plumb.extract.serialize import SerializedClaim, parse_claims, serialize_claims
from plumb.extract.value import parse_value


def claim(text: str, metric: str, units: str | None = None, start: int = 0, **hints) -> Claim:
    return Claim(
        reported_value=parse_value(text), units=units, metric=metric,
        location=CharSpan(start, start + len(text)),
        artifact_hint=hints.get("artifact_hint"), tolerance_hint=hints.get("tolerance_hint"),
    )


# Tests construct claims directly; only src/plumb/extract is held to the single-door rule.
EVERY_VARIANT = [
    claim("0.870", "AUC"),
    claim("p < 0.001", "p-value", start=10),
    claim("0.85 ± 0.03", "accuracy", units="%", start=20),
    claim("95% CI [0.81, 0.89]", "odds ratio", start=40),
    claim("12–15%", "reduction", start=70, artifact_hint="results.json"),
    claim("~10,000", "participants", start=90, tolerance_hint="to within 5%"),
]


def paper_with(claims: list[Claim]) -> str:
    """A paper whose text holds each claim's value verbatim at its span, blanks elsewhere."""
    text = [" "] * 120
    for c in claims:
        text[c.location.start:c.location.end] = list(c.reported_value.text)
    return normalize_text("".join(text))


TEXT = paper_with(EVERY_VARIANT)
PAPER = hash_paper(TEXT)


def test_the_round_trip_is_the_identity() -> None:
    data = serialize_claims(EVERY_VARIANT, paper_hash=PAPER)
    records, paper_hash = parse_claims(data)
    assert paper_hash == PAPER
    assert all(type(r) is SerializedClaim for r in records)
    claims = readmit(records, normalized_text=TEXT)
    assert sorted(claims, key=lambda c: c.id) == sorted(EVERY_VARIANT, key=lambda c: c.id)
    assert serialize_claims(claims, paper_hash=paper_hash) == data


def test_decimals_come_back_exact() -> None:
    (record,), _ = parse_claims(serialize_claims([claim("0.870", "AUC")], paper_hash=PAPER))
    assert record.reported_value.value == Decimal("0.870")
    assert record.reported_value.value.as_tuple().exponent == -3


def test_a_record_the_paper_does_not_ground_is_refused() -> None:
    records, _ = parse_claims(serialize_claims([claim("0.870", "AUC", start=3)], paper_hash=PAPER))
    with pytest.raises(ValueError, match="does not re-admit"):
        readmit(records, normalized_text=TEXT)


def test_a_record_whose_id_does_not_recompute_is_refused() -> None:
    (record,), _ = parse_claims(serialize_claims([claim("0.870", "AUC")], paper_hash=PAPER))
    forged = SerializedClaim(**{**{f: getattr(record, f) for f in record.__slots__}, "id": "0" * 64})
    with pytest.raises(ValueError, match="does not match"):
        readmit([forged], normalized_text=TEXT)


def mutated(mutate) -> bytes:
    doc = json.loads(serialize_claims([claim("0.870", "AUC")], paper_hash=PAPER))
    mutate(doc)
    return json.dumps(doc).encode()


@pytest.mark.parametrize(
    ("why", "mutate"),
    [
        ("id not a string", lambda d: d["claims"][0].update(id=7)),
        ("unknown value kind", lambda d: d["claims"][0]["reported_value"].update(kind="odds")),
        ("decimal as a number", lambda d: d["claims"][0]["reported_value"].update(value=0.87)),
        ("decimal not a decimal", lambda d: d["claims"][0]["reported_value"].update(value="x")),
        ("extra claim field", lambda d: d["claims"][0].update(confidence="0.9")),
        ("missing claim field", lambda d: d["claims"][0].pop("units")),
        ("unknown location kind", lambda d: d["claims"][0]["location"].update(kind="page_box")),
        ("bad paper hash", lambda d: d["paper_hash"].update(digest="abc")),
        ("wrong algorithm", lambda d: d["paper_hash"].update(algorithm="md5")),
        ("extra top-level field", lambda d: d.update(version=1)),
    ],
)
def test_anything_else_is_refused(why: str, mutate) -> None:
    with pytest.raises(ValueError):
        parse_claims(mutated(mutate))


@pytest.mark.parametrize("data", [b"", b"not json", b"[]", b"\xff"])
def test_non_documents_are_refused(data: bytes) -> None:
    with pytest.raises(ValueError):
        parse_claims(data)
