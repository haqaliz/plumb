"""The corpus causes are a closed vocabulary (Phase 1, house catalogue style).

The store refuses a bank or a read with exactly one of these names — never a
generic failure and never a silent acceptance. Nothing in Phase 1 emits them
yet; the store semantics (Phase 2) are their first emission point.
"""

from __future__ import annotations

from plumb.corpus.causes import CAUSES, CASE_CONFLICT, CASE_INVALID, CASE_TAMPERED


def test_the_vocabulary_is_closed_and_exact() -> None:
    assert isinstance(CAUSES, frozenset)
    assert CAUSES == frozenset({CASE_CONFLICT, CASE_TAMPERED, CASE_INVALID})
    assert len(CAUSES) == 3
    assert all(isinstance(c, str) for c in CAUSES)
    assert CASE_CONFLICT != CASE_TAMPERED != CASE_INVALID


def test_each_cause_names_a_distinct_refusal() -> None:
    assert CASE_CONFLICT == "CASE_CONFLICT"
    assert CASE_TAMPERED == "CASE_TAMPERED"
    assert CASE_INVALID == "CASE_INVALID"