"""The corpus case record: content-addressed identity and canonical bytes (Phase 1).

`derive_case_id` is the load-bearing contract — the bank and benchmark aspects
read it, and a case's identity must be a pure function of the recorded members:
same members, same id, in every process and at every hash seed. Labels are
human annotations and live outside identity (`has_labels` marks presence in
the manifest but never enters the id); a record without a paper hashes a
`null` paper_hash, distinct from any hash value.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
import re

import pytest

from plumb.corpus.case import (
    FORMAT,
    MEMBER_KEYS,
    Case,
    derive_case_id,
    hash_bytes,
    objects_tree_hash,
    parse_case,
    serialize_case,
)

_JSON = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "allow_nan": False,
}


def h64(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def members(**overrides: str) -> dict[str, str]:
    base = {
        "claims": h64("claims"),
        "bindings": h64("bindings"),
        "trace": h64("trace"),
        "verdicts": h64("verdicts"),
    }
    base.update(overrides)
    return base


def make_case(
    paper_hash: str | None = h64("paper"),
    run_id: str = h64("run"),
    member_hashes: dict[str, str] | None = None,
    objects_tree_hash: str = h64("objects"),
    has_labels: bool = False,
) -> Case:
    member_hashes = members() if member_hashes is None else member_hashes
    return Case(
        format=FORMAT,
        case_id=derive_case_id(paper_hash, run_id, member_hashes, objects_tree_hash),
        paper_hash=paper_hash,
        run_id=run_id,
        member_hashes=member_hashes,
        objects_tree_hash=objects_tree_hash,
        has_labels=has_labels,
    )


def test_identical_members_produce_identical_case_ids() -> None:
    a = derive_case_id(h64("paper"), h64("run"), members(), h64("objects"))
    b = derive_case_id(h64("paper"), h64("run"), members(), h64("objects"))
    assert a == b
    assert a == make_case().case_id
    assert re.fullmatch(r"[0-9a-f]{64}", a)


def test_case_id_is_the_documented_sha256() -> None:
    c = make_case()
    parts = [FORMAT, c.paper_hash, c.run_id, c.member_hashes, c.objects_tree_hash]
    expected = hashlib.sha256(json.dumps(parts, **_JSON).encode("utf-8")).hexdigest()
    assert c.case_id == expected


def test_any_single_member_differing_changes_the_id() -> None:
    baseline = derive_case_id(h64("paper"), h64("run"), members(), h64("objects"))
    for key in ("claims", "bindings", "trace", "verdicts"):
        changed = members(**{key: h64("other-" + key)})
        assert derive_case_id(h64("paper"), h64("run"), changed, h64("objects")) != baseline
    assert derive_case_id(h64("other-paper"), h64("run"), members(), h64("objects")) != baseline
    assert derive_case_id(h64("paper"), h64("other-run"), members(), h64("objects")) != baseline
    assert derive_case_id(h64("paper"), h64("run"), members(), h64("other-objects")) != baseline


def test_nonclaims_presence_and_value_are_identity() -> None:
    baseline = derive_case_id(h64("paper"), h64("run"), members(), h64("objects"))
    with_nonclaims = members(nonclaims=h64("nonclaims"))
    assert derive_case_id(h64("paper"), h64("run"), with_nonclaims, h64("objects")) != baseline
    other_nonclaims = members(nonclaims=h64("other-nonclaims"))
    assert derive_case_id(h64("paper"), h64("run"), other_nonclaims, h64("objects")) != derive_case_id(
        h64("paper"), h64("run"), with_nonclaims, h64("objects")
    )


def test_labels_never_affect_case_id() -> None:
    unlabeled = make_case(has_labels=False)
    labeled = make_case(has_labels=True)
    assert unlabeled.case_id == labeled.case_id
    assert serialize_case(unlabeled) != serialize_case(labeled)
    a = json.loads(serialize_case(unlabeled))
    b = json.loads(serialize_case(labeled))
    a.pop("has_labels")
    b.pop("has_labels")
    assert a == b


def test_paper_hash_null_vs_value_distinct() -> None:
    no_paper = make_case(paper_hash=None)
    with_paper = make_case(paper_hash=h64("paper"))
    assert no_paper.case_id != with_paper.case_id
    assert json.loads(serialize_case(no_paper))["paper_hash"] is None
    assert json.loads(serialize_case(with_paper))["paper_hash"] == h64("paper")
    assert serialize_case(no_paper) != serialize_case(with_paper)


def test_paper_hash_empty_string_is_refused() -> None:
    with pytest.raises(ValueError):
        derive_case_id("", h64("run"), members(), h64("objects"))


def test_member_hash_keys_are_closed() -> None:
    assert MEMBER_KEYS == ("claims", "bindings", "trace", "verdicts", "nonclaims")
    with pytest.raises(ValueError):
        derive_case_id(None, h64("run"), {**members(), "labels": h64("labels")}, h64("objects"))
    with pytest.raises(ValueError):
        derive_case_id(None, h64("run"), {k: v for k, v in members().items() if k != "claims"}, h64("objects"))


def test_manifest_bytes_are_canonical() -> None:
    data = serialize_case(make_case())
    assert data.endswith(b"\n") and data.count(b"\n") == 1
    doc = json.loads(data)
    assert data == (json.dumps(doc, **_JSON) + "\n").encode("utf-8")


def test_manifest_key_set_is_exact_and_sorted() -> None:
    doc = json.loads(serialize_case(make_case()))
    assert list(doc) == [
        "case_id",
        "format",
        "has_labels",
        "member_hashes",
        "objects_tree_hash",
        "paper_hash",
        "run_id",
    ]


def test_member_hashes_document_is_sorted_and_minimal() -> None:
    doc = json.loads(serialize_case(make_case()))
    assert list(doc["member_hashes"]) == ["bindings", "claims", "trace", "verdicts"]
    with_nonclaims = make_case(member_hashes=members(nonclaims=h64("nonclaims")))
    assert list(json.loads(serialize_case(with_nonclaims))["member_hashes"]) == [
        "bindings",
        "claims",
        "nonclaims",
        "trace",
        "verdicts",
    ]


def test_manifest_leaves_no_machine_state(tmp_path: Path) -> None:
    text = serialize_case(make_case()).decode()
    assert str(tmp_path) not in text
    assert "time" not in text and "path" not in text


def test_objects_tree_hash_is_deterministic_over_the_set() -> None:
    objs = [h64("a"), h64("b"), h64("c")]
    assert objects_tree_hash(objs) == objects_tree_hash(list(reversed(objs)))
    assert objects_tree_hash(objs) == objects_tree_hash([h64("b"), h64("c"), h64("a")])
    assert objects_tree_hash(objs + [h64("a")]) == objects_tree_hash(objs)
    assert objects_tree_hash(objs) != objects_tree_hash(objs[:-1])
    assert objects_tree_hash([]) == objects_tree_hash([])
    assert re.fullmatch(r"[0-9a-f]{64}", objects_tree_hash(objs))


def test_hash_bytes_is_the_sha256_of_the_bytes() -> None:
    data = b"plumb\n"
    assert hash_bytes(data) == hashlib.sha256(data).hexdigest()
    assert hash_bytes(b"") == hashlib.sha256(b"").hexdigest()


def test_serialize_parse_round_trip() -> None:
    for candidate in (
        make_case(),
        make_case(paper_hash=None),
        make_case(member_hashes=members(nonclaims=h64("nonclaims"))),
    ):
        assert parse_case(serialize_case(candidate)) == candidate


def test_parse_refuses_a_case_id_that_does_not_match_its_members() -> None:
    doc = json.loads(serialize_case(make_case()))
    doc["case_id"] = h64("forged")
    with pytest.raises(ValueError):
        parse_case((json.dumps(doc, **_JSON) + "\n").encode("utf-8"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc.update(format="plumb-corpus-case/0"),
        lambda doc: doc.pop("run_id"),
        lambda doc: doc.update(run_id=7),
        lambda doc: doc.update(paper_hash=7),
        lambda doc: doc.update(paper_hash="short"),
        lambda doc: doc.update(objects_tree_hash="zz"),
        lambda doc: doc.update(has_labels="yes"),
        lambda doc: doc.update(has_labels=1),
        lambda doc: doc["member_hashes"].pop("claims"),
        lambda doc: doc["member_hashes"].update(labels=h64("labels")),
        lambda doc: doc["member_hashes"].update(claims=0.0),
        lambda doc: doc["member_hashes"].update(claims="short"),
    ],
)
def test_parse_refuses_a_malformed_manifest(mutate) -> None:
    doc = json.loads(serialize_case(make_case()))
    mutate(doc)
    with pytest.raises(ValueError):
        parse_case((json.dumps(doc, **_JSON) + "\n").encode("utf-8"))


def test_parse_refuses_non_json_bytes() -> None:
    with pytest.raises(ValueError):
        parse_case(b"not json")
    with pytest.raises(ValueError):
        parse_case(b"\xff\xfe")


def test_serialize_refuses_foreign_types() -> None:
    c = make_case()
    with pytest.raises(TypeError):
        serialize_case(
            Case(
                format=FORMAT,
                case_id=c.case_id,
                paper_hash=None,
                run_id=c.run_id,
                member_hashes={**c.member_hashes, "claims": 0.0},
                objects_tree_hash=c.objects_tree_hash,
                has_labels=False,
            )
        )
    with pytest.raises(TypeError):
        serialize_case(
            Case(
                format=FORMAT,
                case_id=c.case_id,
                paper_hash=None,
                run_id=c.run_id,
                member_hashes={**c.member_hashes, "claims": Decimal("1")},
                objects_tree_hash=c.objects_tree_hash,
                has_labels=False,
            )
        )
    with pytest.raises(TypeError):
        serialize_case(
            Case(
                format=FORMAT,
                case_id=c.case_id,
                paper_hash=None,
                run_id=c.run_id,
                member_hashes=c.member_hashes,
                objects_tree_hash=c.objects_tree_hash,
                has_labels=1,
            )
        )
    with pytest.raises(TypeError):
        serialize_case(
            Case(
                format=FORMAT,
                case_id=7,
                paper_hash=None,
                run_id=c.run_id,
                member_hashes=c.member_hashes,
                objects_tree_hash=c.objects_tree_hash,
                has_labels=False,
            )
        )