"""The C4 cause vocabulary is closed, and it is exactly the PRD's (M5).

Every `UNVERIFIED` verdict names one of these causes. The set is the union of the
causes C2/C3 already produce and the ones binding and comparison add; a cause
outside it is a bug, not a new kind of verdict. Two names from `ARCHITECTURE.md`
are reserved for a proposer that does not exist yet and are never emitted.
"""

from __future__ import annotations

from plumb.run import causes as run_causes
from plumb.verify import causes

#: `docs/planning/binding-verdict/prd.md` M5, verbatim.
PRD_M5 = {
    "WONT_RUN",
    "TIMEOUT",
    "NO_ARTIFACT",
    "STALE_ARTIFACT",
    "ENTRYPOINT_MISSING",
    "ENTRYPOINT_AMBIGUOUS",
    "ENV_BUILD_FAILED",
    "NO_BINDING",
    "AMBIGUOUS_BINDING",
    "BINDING_INVALID",
    "UNPARSEABLE_VALUE",
    "NO_TOLERANCE",
    "UNSUPPORTED_VALUE_KIND",
    "UNIT_UNDECLARED",
    "PRECISION_AMBIGUOUS",
    "ARTIFACT_PRECISION_COARSER",
}


def test_the_vocabulary_is_exactly_the_prd_list() -> None:
    assert causes.CAUSES == frozenset(PRD_M5)


def test_every_name_is_a_module_constant_spelled_as_its_value() -> None:
    for name in PRD_M5:
        assert getattr(causes, name) == name


def test_run_causes_are_the_run_packages_own_strings() -> None:
    assert causes.WONT_RUN is run_causes.WONT_RUN
    assert causes.TIMEOUT is run_causes.TIMEOUT
    assert causes.NO_ARTIFACT is run_causes.NO_ARTIFACT
    assert causes.STALE_ARTIFACT is run_causes.STALE_ARTIFACT
    assert causes.ENTRYPOINT_MISSING == run_causes.EntryPointMissing.cause
    assert causes.ENTRYPOINT_AMBIGUOUS == run_causes.EntryPointAmbiguous.cause


def test_proposer_causes_are_reserved_and_never_in_the_vocabulary() -> None:
    assert causes.RESERVED == frozenset({"PROPOSER_UNGROUNDED", "MODEL_ONLY_SIGNAL"})
    assert not causes.RESERVED & causes.CAUSES


def test_binding_invalid_is_a_named_value_error() -> None:
    assert issubclass(causes.BindingInvalid, ValueError)
