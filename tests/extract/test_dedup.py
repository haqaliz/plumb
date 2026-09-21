"""Tests for value-identity dedup.

Dedup answers one question: *are these two mentions the same result?* The answer is
**pure string identity** on `(reported_value.text, metric, units)` — the same three
fields `Claim.id` is derived from, so "same id ⇒ merged, different id ⇒ not merged"
holds exactly rather than approximately.

Three boundary cases are closed decisions (plan §0) and the tests below pin them so
they cannot be re-opened by a well-meaning normalization:

- `0.87` and `0.870` stay **two** claims. The difference is significant figures, which
  is semantic. Merging them is risk R2 — a false `DIVERGED` seeded upstream.
- `.87` and `0.87` stay **two** claims. "Same characters = same claim" is a rule a
  third party can reimplement from one sentence, which C6's independent replay needs.
- Numeric canonicalization is forbidden. `Decimal("0.870") == Decimal("0.87")` is
  `True`, so a `Decimal`-keyed identity would silently fuse the first pair.

Ordering is asserted hard, including across processes. `PYTHONHASHSEED` varies per
interpreter, so a single-process ordering test passes while the contract is broken.
"""

import subprocess
import sys
from dataclasses import FrozenInstanceError
from decimal import Decimal
from itertools import permutations

import pytest

from plumb.extract.claim import Claim
from plumb.extract.dedup import (
    MergedClaim,
    _identity_sort_key,
    _member_sort_key,
    _optional_sort_key,
    claim_identity,
    dedup_claims,
    group_claims,
    merged_locations,
)
from plumb.extract.location import CharSpan, Location
from plumb.extract.value import ClaimValue, Point, parse_value


def value(text: str) -> ClaimValue:
    """`parse_value` that fails the test rather than returning `None` into a fixture."""
    parsed = parse_value(text)
    assert parsed is not None, f"fixture text did not parse: {text!r}"
    return parsed


def claim(**overrides: object) -> Claim:
    """A fully-specified `Claim`, with named fields replaced per test."""
    fields: dict[str, object] = {
        "reported_value": value("0.87"),
        "units": None,
        "metric": "AUC",
        "location": CharSpan(18, 22),
        "artifact_hint": None,
        "tolerance_hint": None,
    }
    fields.update(overrides)
    return Claim(**fields)  # type: ignore[arg-type]


class TestIdentityMatchesTheId:
    """The invariant the whole aspect leans on: identity and `id` agree, exactly."""

    def test_identity_is_value_text_metric_and_units(self) -> None:
        assert claim().reported_value.text == "0.87"
        assert claim_identity(claim(units="%", metric="F1")) == ("0.87", "F1", "%")

    def test_identity_keeps_none_units_distinct_from_empty_units(self) -> None:
        """`None` (dimensionless) and `""` (someone wrote an empty string) differ.

        `Claim.id` already distinguishes them; identity must not re-collapse what the
        record layer went out of its way to keep apart.
        """
        assert claim_identity(claim(units=None)) != claim_identity(claim(units=""))

    @pytest.mark.parametrize(
        "overrides",
        [
            {"location": CharSpan(404, 408)},
            {"artifact_hint": "notebooks/eval.ipynb"},
            {"tolerance_hint": "±0.01"},
        ],
    )
    def test_identity_agrees_with_id_on_fields_the_id_ignores(
        self, overrides: dict[str, object]
    ) -> None:
        first, second = claim(), claim(**overrides)

        assert first.id == second.id
        assert claim_identity(first) == claim_identity(second)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"reported_value": value("0.870")},
            {"metric": "F1"},
            {"units": "%"},
        ],
    )
    def test_identity_agrees_with_id_on_fields_the_id_covers(
        self, overrides: dict[str, object]
    ) -> None:
        first, second = claim(), claim(**overrides)

        assert first.id != second.id
        assert claim_identity(first) != claim_identity(second)


class TestBoundariesThatMustNotMerge:
    """Plan §0. Each of these is a closed decision, not a tuning knob."""

    def test_0_87_and_0_870_stay_two_claims(self) -> None:
        """Significant figures are semantic; merging them is risk R2.

        The two `Decimal`s compare equal, which is exactly why identity is keyed on
        the verbatim text instead.
        """
        two_figures, three_figures = value("0.87"), value("0.870")
        assert two_figures.value == three_figures.value  # type: ignore[attr-defined]

        groups = group_claims(
            [claim(reported_value=two_figures), claim(reported_value=three_figures)]
        )

        assert len(groups) == 2

    def test_bare_point_87_and_0_87_stay_two_claims(self) -> None:
        """Identity is pure string identity, so a leading zero is a different claim."""
        groups = group_claims(
            [claim(reported_value=value(".87")), claim(reported_value=value("0.87"))]
        )

        assert len(groups) == 2

    def test_claims_differing_only_in_units_stay_separate(self) -> None:
        groups = group_claims([claim(units="%"), claim(units="pp")])

        assert len(groups) == 2

    def test_none_units_and_empty_units_stay_separate(self) -> None:
        groups = group_claims([claim(units=None), claim(units="")])

        assert len(groups) == 2

    def test_claims_differing_only_in_metric_stay_separate(self) -> None:
        groups = group_claims([claim(metric="AUC"), claim(metric="F1")])

        assert len(groups) == 2


class TestGrouping:
    def test_two_claims_identical_but_for_location_group_together(self) -> None:
        """The case dedup exists for: one result, reported in two places."""
        abstract = claim(location=CharSpan(18, 22))
        table = claim(location=CharSpan(404, 408))

        groups = group_claims([abstract, table])

        assert len(groups) == 1
        assert groups[0] == (abstract, table)

    def test_claims_differing_only_in_hints_group_together(self) -> None:
        """Hints say how to check a claim, not which claim it is — as the id agrees."""
        groups = group_claims(
            [claim(artifact_hint="src/train.py"), claim(tolerance_hint="±0.01")]
        )

        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_empty_input_produces_no_groups(self) -> None:
        assert group_claims([]) == ()

    def test_a_single_claim_produces_one_group_of_one(self) -> None:
        only = claim()

        assert group_claims([only]) == ((only,),)

    def test_non_ascii_text_groups_by_exact_characters(self) -> None:
        """`μ` and `u` are different characters, therefore different claims."""
        groups = group_claims([claim(units="μg"), claim(units="ug")])

        assert len(groups) == 2

    def test_a_non_claim_is_rejected_rather_than_grouped(self) -> None:
        with pytest.raises(TypeError):
            group_claims([claim(), ("0.87", "AUC", None)])  # type: ignore[list-item]


class TestMergedLocations:
    """What locations a merged claim carries — independent of the record that holds
    them, so this is settled before the representation is."""

    def test_locations_are_sorted_by_start_then_end(self) -> None:
        late = claim(location=CharSpan(404, 408))
        early = claim(location=CharSpan(18, 22))
        same_start_longer = claim(location=CharSpan(18, 30))

        assert merged_locations([late, same_start_longer, early]) == (
            CharSpan(18, 22),
            CharSpan(18, 30),
            CharSpan(404, 408),
        )

    def test_claims_identical_in_every_field_including_location_yield_one_location(
        self,
    ) -> None:
        """Plan §5: merge to one location, not to a duplicated one.

        The same claim extracted twice from the same span is one mention, and a
        merged record that listed its location twice would claim the paper said it
        twice.
        """
        twice = [claim(), claim()]

        assert group_claims(twice) == (tuple(twice),)
        assert merged_locations(twice) == (CharSpan(18, 22),)

    def test_an_unorderable_location_variant_is_refused_not_guessed(self) -> None:
        """`CharSpan` is the only variant today; a new one must extend the ordering.

        Silently ordering an unknown variant by insertion would make output order
        depend on extraction order, which is the nondeterminism this aspect exists to
        remove.
        """

        class PageBox(Location):
            __slots__ = ()
            kind = "page_box"

            def __init__(self) -> None:
                pass

        with pytest.raises(TypeError):
            merged_locations([claim(location=PageBox())])


class TestDeterministicOrdering:
    """Ordering is asserted against an explicit total key — never insertion, never
    `set` iteration, never `hash()`."""

    def _mixed(self) -> list[Claim]:
        """Claims spanning every axis the sort key must totally order."""
        return [
            claim(reported_value=value("0.870"), location=CharSpan(404, 408)),
            claim(units="%", location=CharSpan(18, 22)),
            claim(units=None, location=CharSpan(18, 22)),
            claim(units="", location=CharSpan(18, 22)),
            claim(metric="F1", location=CharSpan(9, 12)),
            claim(location=CharSpan(404, 408), artifact_hint="src/train.py"),
            claim(location=CharSpan(18, 22)),
        ]

    def test_every_input_permutation_produces_identical_output(self) -> None:
        claims = self._mixed()
        expected = group_claims(claims)

        for permutation in permutations(claims):
            assert group_claims(list(permutation)) == expected

    def test_none_and_empty_units_order_stably_against_each_other(self) -> None:
        """The trap in a `units or ""` sort key.

        `None or ""` is `""`, so that key makes these two claims tie — and a tie in a
        key that is supposed to be *total* falls back to input order, which is not
        guaranteed to be stable across runs.
        """
        dimensionless, empty = claim(units=None), claim(units="")

        forward = group_claims([dimensionless, empty])
        backward = group_claims([empty, dimensionless])

        assert forward == backward

    def test_order_is_identical_across_processes_with_different_hash_seeds(
        self,
    ) -> None:
        """The load-bearing one: `PYTHONHASHSEED` varies per interpreter.

        A single-process test cannot see a `set`- or `hash()`-derived ordering,
        because one process has one seed. `subprocess` is deliberately outside
        `conftest.py`'s same-process network guard (documented there), and nothing
        here reaches outward — it spawns this same interpreter and reads stdout.
        """
        program = (
            "from plumb.extract.claim import Claim\n"
            "from plumb.extract.dedup import claim_identity, group_claims\n"
            "from plumb.extract.location import CharSpan\n"
            "from plumb.extract.value import parse_value\n"
            "def c(t, units, metric, start):\n"
            "    return Claim(reported_value=parse_value(t), units=units,\n"
            "                 metric=metric, location=CharSpan(start, start + 4),\n"
            "                 artifact_hint=None, tolerance_hint=None)\n"
            "claims = [c('0.870', None, 'AUC', 404), c('0.87', '%', 'AUC', 18),\n"
            "          c('0.87', None, 'AUC', 18), c('0.87', '', 'AUC', 18),\n"
            "          c('0.87', None, 'F1', 9), c('0.87', None, 'AUC', 404)]\n"
            "for group in group_claims(claims):\n"
            "    print(claim_identity(group[0]),\n"
            "          [(m.location.start, m.location.end) for m in group])\n"
        )
        outputs = {
            seed: subprocess.run(
                [sys.executable, "-c", program],
                capture_output=True,
                check=True,
                env={"PYTHONHASHSEED": seed, "PATH": "", "PYTHONPATH": _src_root()},
            ).stdout
            for seed in ("0", "1", "4242")
        }

        assert len(set(outputs.values())) == 1, outputs


def _src_root() -> str:
    """`src/` on this checkout, so the child interpreter imports the same code."""
    import plumb

    return str(__import__("pathlib").Path(plumb.__file__).parent.parent)


class TestNoVerdicts:
    def test_dedup_emits_no_verdict_vocabulary(self) -> None:
        """`CLAUDE.md` #1: this module records mentions, it decides nothing."""
        from pathlib import Path

        import plumb.extract.dedup as dedup

        source = Path(dedup.__file__).read_text(encoding="utf-8")
        for verdict in ("REPRODUCED", "WITHIN-TOLERANCE", "DIVERGED", "UNVERIFIED"):
            assert verdict not in source.replace("`" + verdict + "`", "")


class TestValueConflict:
    """Same identity, different parsed number — an upstream inconsistency."""

    def test_same_text_with_different_decimals_is_refused_not_silently_picked(
        self,
    ) -> None:
        """Identity is keyed on `text`, so these two share an id but disagree.

        Only a hand-built `ClaimValue` can reach this state (`parse_value` is a
        function of the text), which makes it a bug upstream. Merging it by keeping
        whichever sorted first would discard a parse silently — the "silent pass"
        `CLAUDE.md` #3 rules out. It fails loudly instead.
        """
        honest = claim(reported_value=Point(text="0.87", value=Decimal("0.87")))
        wrong = claim(reported_value=Point(text="0.87", value=Decimal("99")))

        assert honest.id == wrong.id

        with pytest.raises(ValueError, match="reported_value"):
            group_claims([honest, wrong])


# --------------------------------------------------------------------------------
# The merged record. `MergedClaim` is a *result* — one value, N places — where a
# `Claim` is a *mention*. They are separate types on purpose; see `dedup.py`.
# --------------------------------------------------------------------------------


MERGED_FIELDS = (
    "id",
    "reported_value",
    "units",
    "metric",
    "locations",
    "artifact_hints",
    "tolerance_hints",
)


def merged(**overrides: object) -> MergedClaim:
    """A fully-specified `MergedClaim`, with named fields replaced per test."""
    fields: dict[str, object] = {
        "id": claim().id,
        "reported_value": value("0.87"),
        "units": None,
        "metric": "AUC",
        "locations": (CharSpan(18, 22),),
        "artifact_hints": (),
        "tolerance_hints": (),
    }
    fields.update(overrides)
    return MergedClaim(**fields)  # type: ignore[arg-type]


class TestMergedClaimShape:
    """Aspect 1's conventions, applied to a new record: frozen, slots, no defaults."""

    @pytest.mark.parametrize("missing", MERGED_FIELDS)
    def test_every_field_must_be_stated(self, missing: str) -> None:
        fields = {
            "id": claim().id,
            "reported_value": value("0.87"),
            "units": None,
            "metric": "AUC",
            "locations": (CharSpan(18, 22),),
            "artifact_hints": (),
            "tolerance_hints": (),
        }
        del fields[missing]

        with pytest.raises(TypeError):
            MergedClaim(**fields)  # type: ignore[arg-type]

    def test_the_record_is_frozen(self) -> None:
        with pytest.raises(FrozenInstanceError):
            merged().metric = "F1"  # type: ignore[misc]

    def test_the_record_is_sealed_against_injected_attributes(self) -> None:
        """`slots=True` with no `__dict__`, so no later stage can bolt a field on.

        The field that must never appear is `confidence` — a model's opinion standing
        in for a re-derived value (`CLAUDE.md` #1). `Claim` is sealed against it and a
        merged claim is an equally attractive place to smuggle it in.
        """
        with pytest.raises((AttributeError, TypeError)):
            object.__setattr__(merged(), "confidence", 0.95)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"id": 17},
            {"id": ""},
            {"reported_value": "0.87"},
            {"metric": ""},
            {"metric": None},
            {"units": 5},
            {"locations": [CharSpan(18, 22)]},
            {"locations": ()},
            {"locations": (CharSpan(18, 22), "somewhere")},
            {"artifact_hints": "src/train.py"},
            {"artifact_hints": (None,)},
            {"tolerance_hints": ["±0.01"]},
        ],
    )
    def test_malformed_fields_are_refused(self, overrides: dict[str, object]) -> None:
        with pytest.raises((TypeError, ValueError)):
            merged(**overrides)

    def test_locations_must_be_a_tuple_not_a_list(self) -> None:
        """A list would be mutable and unhashable, unsealing a frozen record."""
        with pytest.raises(TypeError):
            merged(locations=[CharSpan(18, 22)])

    def test_locations_must_be_sorted_and_distinct(self) -> None:
        """The determinism invariant of this whole aspect, enforced on the record.

        A hand-built record with out-of-order locations would serialize differently
        from the identical record built by `dedup_claims`, which is exactly the
        input-order dependence this module exists to remove.
        """
        with pytest.raises(ValueError):
            merged(locations=(CharSpan(404, 408), CharSpan(18, 22)))
        with pytest.raises(ValueError):
            merged(locations=(CharSpan(18, 22), CharSpan(18, 22)))

    def test_hints_must_be_sorted_and_distinct(self) -> None:
        with pytest.raises(ValueError):
            merged(artifact_hints=("src/train.py", "notebooks/eval.ipynb"))
        with pytest.raises(ValueError):
            merged(tolerance_hints=("±0.01", "±0.01"))


class TestIdIsCarriedNotDerived:
    def test_the_merged_id_matches_every_member_of_the_group(self) -> None:
        group = [claim(location=CharSpan(18, 22)), claim(location=CharSpan(404, 408))]

        (result,) = dedup_claims(group)

        assert result.id == group[0].id == group[1].id

    def test_the_id_is_carried_verbatim_rather_than_re_derived(self) -> None:
        """`Claim.id` excludes `location` (D2), so every member already shares it.

        Re-deriving would duplicate the hashing rule in a second place, where it could
        drift. A deliberately wrong-but-well-shaped digest proves the field is a
        carrier: if anything re-derived it, this value could not survive.
        """
        sentinel = "0" * 64

        assert merged(id=sentinel).id == sentinel
        assert sentinel != claim().id

    def test_the_id_derivation_rule_exists_in_one_module_only(self) -> None:
        """The check that a behavioural test cannot make.

        Because `Claim.id` excludes `location`, re-deriving the id here would produce
        the *same* string as carrying it — no assertion on output could tell them
        apart. What is checkable is that the rule is not copied: this module hashes
        nothing, so it has nothing that could drift from `claim.py`.
        """
        from pathlib import Path

        import plumb.extract.dedup as dedup

        source = Path(dedup.__file__).read_text(encoding="utf-8")

        assert "hashlib" not in source
        assert "_derive_id" not in source


class TestHintMerging:
    """Hints are non-authoritative, so losing one is silent information loss."""

    def test_distinct_hints_are_kept_and_sorted(self) -> None:
        """The abstract-plus-table case, which is normal rather than exceptional."""
        group = [
            claim(location=CharSpan(404, 408), artifact_hint="src/train.py"),
            claim(location=CharSpan(18, 22), artifact_hint="notebooks/eval.ipynb"),
        ]

        (result,) = dedup_claims(group)

        assert result.artifact_hints == ("notebooks/eval.ipynb", "src/train.py")

    def test_duplicate_hints_collapse(self) -> None:
        group = [
            claim(location=CharSpan(18, 22), artifact_hint="src/train.py"),
            claim(location=CharSpan(404, 408), artifact_hint="src/train.py"),
        ]

        (result,) = dedup_claims(group)

        assert result.artifact_hints == ("src/train.py",)

    def test_absent_hints_are_dropped_rather_than_recorded_as_none(self) -> None:
        """`None` means nobody proposed a hint; an empty tuple says that once."""
        group = [
            claim(location=CharSpan(18, 22), artifact_hint=None),
            claim(location=CharSpan(404, 408), artifact_hint="src/train.py"),
        ]

        (result,) = dedup_claims(group)

        assert result.artifact_hints == ("src/train.py",)
        assert dedup_claims([claim()])[0].artifact_hints == ()

    def test_tolerance_hints_merge_the_same_way(self) -> None:
        group = [
            claim(location=CharSpan(404, 408), tolerance_hint="±0.01"),
            claim(location=CharSpan(18, 22), tolerance_hint="within 1%"),
            claim(location=CharSpan(9, 12), tolerance_hint=None),
        ]

        (result,) = dedup_claims(group)

        assert result.tolerance_hints == ("within 1%", "±0.01")


class TestDedupClaims:
    def test_one_merged_claim_per_group(self) -> None:
        results = dedup_claims(
            [claim(), claim(location=CharSpan(404, 408)), claim(metric="F1")]
        )

        assert len(results) == 2
        assert all(isinstance(result, MergedClaim) for result in results)

    def test_a_merged_claim_carries_the_groups_locations(self) -> None:
        results = dedup_claims([claim(location=CharSpan(404, 408)), claim()])

        assert results[0].locations == (CharSpan(18, 22), CharSpan(404, 408))

    def test_identical_claims_merge_to_one_location_not_a_duplicated_one(self) -> None:
        (result,) = dedup_claims([claim(), claim()])

        assert result.locations == (CharSpan(18, 22),)

    def test_empty_input_produces_no_merged_claims(self) -> None:
        assert dedup_claims([]) == ()

    def test_same_id_merges_and_different_id_does_not(self) -> None:
        """The invariant stated in one line, asserted in one line."""
        same = [claim(), claim(location=CharSpan(404, 408))]
        different = [claim(), claim(reported_value=value("0.870"))]

        assert same[0].id == same[1].id and len(dedup_claims(same)) == 1
        assert different[0].id != different[1].id and len(dedup_claims(different)) == 2

    def test_output_order_is_independent_of_input_order(self) -> None:
        claims = [
            claim(reported_value=value("0.870")),
            claim(units="%"),
            claim(units=None),
            claim(units=""),
            claim(metric="F1"),
        ]
        expected = dedup_claims(claims)

        for permutation in permutations(claims):
            assert dedup_claims(list(permutation)) == expected

    def test_a_merged_claim_is_not_accepted_as_input(self) -> None:
        with pytest.raises(TypeError):
            dedup_claims([merged()])  # type: ignore[list-item]


class TestMergedClaimIsNotAClaim:
    """Mirrors `test_study.py`'s `TestNotAClaim`: one must not pass for the other.

    A `Claim` is one mention; a `MergedClaim` is one result across N mentions. The
    singular `location` on `Claim` is what makes "a claim is one mention" enforceable
    at zero cost, and it is given up the moment the two types converge.
    """

    def test_a_merged_claim_is_not_a_claim(self) -> None:
        assert not isinstance(merged(), Claim)

    def test_a_claim_is_not_a_merged_claim(self) -> None:
        assert not isinstance(claim(), MergedClaim)

    def test_the_two_types_share_no_base_class(self) -> None:
        shared = set(MergedClaim.__mro__) & set(Claim.__mro__)

        assert shared == {object}

    @pytest.mark.parametrize(
        "attribute", ["location", "artifact_hint", "tolerance_hint"]
    )
    def test_a_merged_claim_does_not_duck_type_as_a_claim(self, attribute: str) -> None:
        """The singular names are absent, so `merged.location` fails loudly.

        Consuming code reaches for `claim.location` without an `isinstance` check.
        Against a merged record that must raise, not silently return one of several
        places the paper made the claim — the silent-wrong-answer class this project
        treats as worst.
        """
        assert not hasattr(merged(), attribute)

    @pytest.mark.parametrize(
        "attribute", ["locations", "artifact_hints", "tolerance_hints"]
    )
    def test_a_claim_does_not_duck_type_as_a_merged_claim(self, attribute: str) -> None:
        assert not hasattr(claim(), attribute)

    def test_a_merged_claim_is_rejected_where_a_claim_value_is_required(self) -> None:
        with pytest.raises(TypeError):
            claim(reported_value=merged())

    def test_a_claim_is_rejected_where_a_merged_claims_value_is_required(self) -> None:
        with pytest.raises(TypeError):
            merged(reported_value=claim())

    def test_a_merged_claim_is_rejected_where_a_claim_is_required(self) -> None:
        for function in (claim_identity, lambda c: group_claims([c])):
            with pytest.raises(TypeError):
                function(merged())  # type: ignore[arg-type]

    def test_a_merged_claim_never_equals_a_claim(self) -> None:
        assert merged() != claim()


class TestSortKeysDirectly:
    """Assertions on the order keys themselves, with every other component held equal.

    A test that observes only `group_claims`' output cannot distinguish "this key
    component is total" from "some *later* component separated them anyway". The
    member key has exactly that hazard: `artifact_hint` is followed by
    `tolerance_hint`, so a fixture whose tolerance hints differ would pass while the
    artifact-hint component was broken. These tests hold the backstop equal so only
    the component under test can decide the order.

    They reach for private helpers deliberately. The keys *are* the determinism
    contract, and the contract is about to be shared with `serialize.py` — once two
    modules depend on these functions, "it happened to come out right through dedup's
    output" stops being evidence about either of them.
    """

    def test_optional_key_separates_none_from_empty_string(self) -> None:
        """The whole defect in one line: `None or ""` is `""`."""
        assert _optional_sort_key(None) != _optional_sort_key("")

    def test_optional_key_orders_none_before_any_string(self) -> None:
        for present in ("", "a", "±0.01", "\x00"):
            assert _optional_sort_key(None) < _optional_sort_key(present)

    def test_identity_key_separates_none_units_from_empty_units(self) -> None:
        """Units is the last component of the identity key, so nothing can mask it."""
        assert _identity_sort_key(("0.87", "AUC", None)) != _identity_sort_key(
            ("0.87", "AUC", "")
        )

    def test_member_key_separates_hints_with_the_backstop_held_equal(self) -> None:
        """`artifact_hint` must decide on its own, not with `tolerance_hint`'s help."""
        absent = claim(artifact_hint=None, tolerance_hint=None)
        empty = claim(artifact_hint="", tolerance_hint=None)

        assert absent.location == empty.location
        assert absent.tolerance_hint == empty.tolerance_hint
        assert _member_sort_key(absent) != _member_sort_key(empty)

    def test_member_key_separates_tolerance_hints_with_earlier_parts_equal(
        self,
    ) -> None:
        absent = claim(artifact_hint=None, tolerance_hint=None)
        empty = claim(artifact_hint=None, tolerance_hint="")

        assert _member_sort_key(absent) != _member_sort_key(empty)

    def test_no_two_members_of_a_group_share_a_member_key(self) -> None:
        """Totality as a property, over every axis a group member may vary on.

        A shared key between two distinct members is the tie that hands ordering back
        to input order — the failure this whole class exists to make visible.
        """
        members = [
            claim(location=CharSpan(18, 22), artifact_hint=None, tolerance_hint=None),
            claim(location=CharSpan(18, 22), artifact_hint="", tolerance_hint=None),
            claim(location=CharSpan(18, 22), artifact_hint=None, tolerance_hint=""),
            claim(location=CharSpan(18, 22), artifact_hint="a", tolerance_hint=None),
            claim(location=CharSpan(18, 30), artifact_hint=None, tolerance_hint=None),
            claim(location=CharSpan(404, 408), artifact_hint=None, tolerance_hint=None),
        ]

        keys = [_member_sort_key(member) for member in members]

        assert len(keys) == len(set(keys))

    def test_member_ordering_is_input_independent_for_none_versus_empty_hint(
        self,
    ) -> None:
        """The behavioural half, with the backstop held equal so it cannot help."""
        absent = claim(artifact_hint=None, tolerance_hint=None)
        empty = claim(artifact_hint="", tolerance_hint=None)

        assert group_claims([absent, empty]) == group_claims([empty, absent])
