"""The discrepancy corpus: banked, content-addressed, write-once cases (C5, first slice).

`bank_case(record_dir, store_dir)` folds one verify run's record into the
gitignored local store as a case under `<store_dir>/<case_id>/`; `read_case`
returns its members, every byte verified against the manifest's hashes. The
identity (`derive_case_id`) is a pure function of the recorded bytes — labels
never enter it.
"""

from plumb.corpus.case import derive_case_id
from plumb.corpus.causes import (
    CAUSES,
    CASE_CONFLICT,
    CASE_INVALID,
    CASE_TAMPERED,
    CorpusRefused,
)
from plumb.corpus.store import CaseRead, bank_case, read_case

__all__ = [
    "CAUSES",
    "CASE_CONFLICT",
    "CASE_INVALID",
    "CASE_TAMPERED",
    "CaseRead",
    "CorpusRefused",
    "bank_case",
    "derive_case_id",
    "read_case",
]