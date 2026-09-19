"""Tests for the `StudyParameter` record.

The contract under test is mostly a *separation*: a `StudyParameter` is not a `Claim`
and must never be usable as one. That is not tidiness. Reported N has to be extracted,
because C7 (internal-consistency checking) verifies reported statistics against the
reported N — but no execution ever re-derives a sample size, so if N were admitted as a
claim it would sit in the coverage denominator as a claim that can never bind. The
Phase 0 gate number is the fraction of headline claims that bind and re-derive; letting
N into that fraction would understate it for a reason that has nothing to do with how
well Plumb works. Keeping the two types unrelated is what keeps the number honest.

`TestNotAClaim` is therefore the load-bearing class in this file, and
`TestNoIdentityFields` defends two deliberate absences (`id`, `confidence`).

Population — deciding which text becomes a `StudyParameter` — is aspect 2's job. This
aspect builds the shape and nothing else, and emits no verdicts.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from plumb.extract.claim import Claim
from plumb.extract.location import CharSpan, Location
from plumb.extract.study import StudyParameter
from plumb.extract.value import ClaimValue, parse_value

# The sentence the spans below index into, so fixtures stay plausible rather than
# arbitrary integers. The claim in it is the AUC; the `412` is study metadata.
PARAGRAPH = "The model reached AUC 0.87 on the held-out cohort (n = 412)."


def value(text: str) -> ClaimValue:
    """`parse_value` that fails the test rather than returning `None` into a fixture."""
    parsed = parse_value(text)
    assert parsed is not None, f"fixture text did not parse: {text!r}"
    return parsed


def span_of(needle: str) -> CharSpan:
    """The span a correct extractor would emit for `needle` inside `PARAGRAPH`."""
    start = PARAGRAPH.index(needle)
    return CharSpan(start, start + len(needle))


def parameter(**overrides: object) -> StudyParameter:
    """A fully-specified `StudyParameter`, with named fields replaced per test."""
    fields: dict[str, object] = {
        "name": "n",
        "value": value("412"),
        "location": span_of("412"),
    }
    fields.update(overrides)
    return StudyParameter(**fields)  # type: ignore[arg-type]


def claim(**overrides: object) -> Claim:
    """A fully-specified `Claim`, for the separation tests to compare against."""
    fields: dict[str, object] = {
        "reported_value": value("0.87"),
        "units": None,
        "metric": "AUC",
        "location": span_of("0.87"),
        "artifact_hint": None,
        "tolerance_hint": None,
    }
    fields.update(overrides)
    return Claim(**fields)  # type: ignore[arg-type]


class TestConstruction:
    @pytest.mark.parametrize("missing", ["name", "value", "location"])
    def test_every_field_must_be_stated(self, missing: str) -> None:
        """No field has a default. All three are required to mean anything.

        A parameter with no name is unattributable, one with no value records nothing,
        and one with no location cannot be shown to a reader who wants to check it.
        """
        fields: dict[str, object] = {
            "name": "n",
            "value": value("412"),
            "location": span_of("412"),
        }
        del fields[missing]

        with pytest.raises(TypeError):
            StudyParameter(**fields)  # type: ignore[arg-type]

    def test_fields_round_trip_verbatim(self) -> None:
        loc = span_of("412")
        reported = value("412")
        parameter_ = StudyParameter(name="n", value=reported, location=loc)

        assert parameter_.name == "n"
        assert parameter_.value is reported
        assert parameter_.location is loc

    def test_the_value_keeps_the_papers_own_text(self) -> None:
        """A reported N is a reported number, with the same verbatim rule as a claim.

        `1,024` and `1024` are the same count but not the same string, and C7 will want
        to quote what the paper printed, not our re-rendering of it.
        """
        parameter_ = parameter(value=value("1,024"))

        assert parameter_.value.text == "1,024"
        assert parameter_.value.value == Decimal("1024")  # type: ignore[attr-defined]

    @pytest.mark.parametrize("empty", ["", " ", "\t", "\n  "])
    def test_name_must_not_be_empty_or_whitespace(self, empty: str) -> None:
        """An unnamed parameter cannot be looked up by the capability that needs it.

        C7 asks for *the reported N* by name. A nameless record would force a later
        stage to re-read the prose to work out which parameter it holds, which is the
        guessing this project does not do — the same argument that makes `Claim.metric`
        required.
        """
        with pytest.raises(ValueError):
            parameter(name=empty)

    def test_name_must_be_a_string(self) -> None:
        with pytest.raises(TypeError):
            parameter(name=None)

    def test_value_must_be_a_claim_value(self) -> None:
        """A bare string or an int would duck-type just far enough to be wrong."""
        with pytest.raises(TypeError):
            parameter(value="412")

    def test_value_must_not_be_a_bare_decimal(self) -> None:
        """A `Decimal` has lost the verbatim text before it ever reached this record."""
        with pytest.raises(TypeError):
            parameter(value=Decimal("412"))

    def test_location_must_be_a_location(self) -> None:
        with pytest.raises(TypeError):
            parameter(location=(50, 53))


class TestNotAClaim:
    """M11's whole point: the two types are unrelated and one cannot pass for the other.

    Reported N must be extracted — C7 checks reported statistics against it — but it is
    not a claim. It fails both admission tests: it names no metric, and it is not
    asserted about the paper's own *results*; it is study metadata. And no execution
    re-derives a sample size, so counting N as a bindable claim would put a
    permanently-unbindable item into the coverage denominator and distort the Phase 0
    gate number.
    """

    def test_a_study_parameter_is_not_a_claim(self) -> None:
        assert not isinstance(parameter(), Claim)

    def test_a_claim_is_not_a_study_parameter(self) -> None:
        assert not isinstance(claim(), StudyParameter)

    def test_the_two_types_share_no_base_class(self) -> None:
        """No shared ancestor, so no `isinstance` check anywhere can accept both.

        A common base — even an empty marker one — is how the distinction would erode:
        a later stage would type a parameter against the base and start accepting N
        wherever it meant to accept claims.
        """
        shared = set(StudyParameter.__mro__) & set(Claim.__mro__)

        assert shared == {object}

    def test_a_study_parameter_is_rejected_where_a_claim_value_is_required(self) -> None:
        """The one place in this aspect that types its input actually refuses it.

        `Claim.reported_value` is the nearest slot a stray `StudyParameter` could reach,
        and its type check turns the mistake into a loud failure rather than a claim
        whose reported value is a piece of study metadata.
        """
        with pytest.raises(TypeError):
            claim(reported_value=parameter())

    @pytest.mark.parametrize(
        "attribute",
        ["reported_value", "metric", "units", "artifact_hint", "tolerance_hint", "id"],
    )
    def test_a_study_parameter_does_not_duck_type_as_a_claim(
        self, attribute: str
    ) -> None:
        """Separation by field names too, not only by `isinstance`.

        Plenty of consuming code will reach for `claim.metric` or `claim.id` without an
        `isinstance` check first. None of those attribute names exist here, so such
        code fails at the wrong record instead of quietly treating N as a claim.
        """
        assert not hasattr(parameter(), attribute)

    @pytest.mark.parametrize("attribute", ["name"])
    def test_a_claim_does_not_duck_type_as_a_study_parameter(
        self, attribute: str
    ) -> None:
        assert not hasattr(claim(), attribute)

    def test_a_study_parameter_is_not_a_value_or_a_location(self) -> None:
        """It *holds* a value and a location; it is neither."""
        parameter_ = parameter()

        assert not isinstance(parameter_, ClaimValue)
        assert not isinstance(parameter_, Location)

    def test_a_study_parameter_never_equals_a_claim(self) -> None:
        """Even built from the same value and the same span."""
        loc = span_of("0.87")
        reported = value("0.87")

        parameter_ = StudyParameter(name="AUC", value=reported, location=loc)
        claim_ = Claim(
            reported_value=reported,
            units=None,
            metric="AUC",
            location=loc,
            artifact_hint=None,
            tolerance_hint=None,
        )

        assert parameter_ != claim_
        assert claim_ != parameter_


class TestNoIdentityFields:
    """Two absences, each deliberate and each defended by a test.

    `id` is absent because identity and dedup semantics for study parameters are
    undecided. `confidence` is absent for the same guardrail reason it is absent from
    `Claim`: a confidence float becomes a model's opinion standing in for a re-derived
    value, and only execution assigns verdicts (`CLAUDE.md` #1).
    """

    def test_there_is_no_id(self) -> None:
        """Deriving one here would settle a question nobody has asked yet.

        `Claim.id` exists because aspect 3 needs claims reported in several places to
        merge into one record with a stable identity. No such requirement has been
        stated for study parameters: whether two mentions of N merge, and on what key —
        the name, the verbatim value, both — is a decision C7 is entitled to make when
        it is built. Inventing a hash now would look like that decision had been taken,
        and a later stage would build on it.
        """
        assert not hasattr(parameter(), "id")

    def test_an_id_cannot_be_supplied_by_the_caller(self) -> None:
        with pytest.raises(TypeError):
            parameter(id="deadbeef")

    def test_there_is_no_confidence_attribute(self) -> None:
        """A guardrail, not an omission — the same one `Claim` carries.

        A `confidence: float` here becomes `if parameter.confidence > 0.9` at the point
        where C7 decides whether to run its consistency check, which is a model's
        opinion deciding an outcome. A model may propose that a number is the reported
        N; only execution assigns verdicts. An extractor that wants to record how sure
        it was keeps that in its own output, where the verdict layer will not read it.
        """
        assert not hasattr(parameter(), "confidence")

    def test_confidence_cannot_be_passed_to_the_constructor(self) -> None:
        with pytest.raises(TypeError):
            parameter(confidence=0.95)

    @pytest.mark.parametrize("attribute", ["id", "confidence"])
    def test_absent_fields_cannot_be_attached_after_construction(
        self, attribute: str
    ) -> None:
        """Closing the back door: they cannot be set on an instance either.

        The exception *type* is deliberately not pinned. On a frozen dataclass with
        `slots=True`, CPython's generated `__setattr__` closes over the pre-slots class
        object, so assigning an *undeclared* attribute raises a confusing `TypeError`
        from `super()` rather than `FrozenInstanceError` (3.12.13, verified). That is an
        interpreter detail and may change; the invariant this test defends is the one
        asserted last — the attribute does not exist afterwards.
        """
        parameter_ = parameter()

        with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
            setattr(parameter_, attribute, "whatever")

        assert not hasattr(parameter_, attribute)

    @pytest.mark.parametrize("attribute", ["id", "confidence"])
    def test_absent_fields_cannot_be_forced_on_with_object_setattr(
        self, attribute: str
    ) -> None:
        """`slots=True` is load-bearing, not a micro-optimisation.

        Without it the record would carry a `__dict__` and
        `object.__setattr__(parameter, "confidence", 0.9)` would succeed, giving either
        field a way back in through the side door. With slots there is nowhere to put
        it.
        """
        parameter_ = parameter()

        with pytest.raises(AttributeError):
            object.__setattr__(parameter_, attribute, "whatever")


class TestFrozen:
    @pytest.mark.parametrize(
        ("field", "new_value"),
        [
            ("name", "N"),
            ("value", "999"),
            ("location", CharSpan(0, 1)),
        ],
    )
    def test_fields_cannot_be_reassigned(self, field: str, new_value: object) -> None:
        """A record of what a paper reported does not get edited afterwards."""
        parameter_ = parameter()

        with pytest.raises(FrozenInstanceError):
            setattr(parameter_, field, new_value)

    def test_equal_field_values_make_equal_records(self) -> None:
        assert parameter() == parameter()

    def test_records_differing_in_location_are_not_equal(self) -> None:
        """Equality is whole-record and structural — it is *not* a dedup key.

        Two mentions of the same N in different places are two unequal records here.
        Whether they should merge is exactly the open question `test_there_is_no_id`
        describes; this assertion records that nothing in this aspect answers it.
        """
        assert parameter(location=CharSpan(50, 53)) != parameter(
            location=CharSpan(404, 407)
        )

    def test_a_record_is_hashable(self) -> None:
        """Frozen, so it can go in a set — but membership is whole-record equality.

        This is not an identity scheme. It is the dataclass default, stated here so it
        is not mistaken for one.
        """
        assert len({parameter(), parameter()}) == 1
