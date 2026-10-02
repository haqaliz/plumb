"""The closed cause vocabulary of the corpus store.

A bank or a read refuses with exactly one of these names — never a generic
failure and never a silent acceptance. `CASE_CONFLICT` names a re-bank whose
`case_id` matches an existing case but whose bytes differ (tamper, or a
different record hashing identically) — the existing case is untouched;
`CASE_TAMPERED` names a read-back whose stored member bytes no longer match
their manifest hashes — forged bytes are never returned; `CASE_INVALID` names
a malformed manifest or member set. `CorpusRefused` carries the one cause a
bank or a read refused with.
"""

from __future__ import annotations

__all__ = ["CAUSES", "CASE_CONFLICT", "CASE_INVALID", "CASE_TAMPERED", "CorpusRefused"]

#: Same case_id, different bytes: the existing case is refused, never overwritten.
CASE_CONFLICT = "CASE_CONFLICT"
#: A stored member no longer matches its manifest hash; its bytes are never read.
CASE_TAMPERED = "CASE_TAMPERED"
#: The manifest or members are malformed; nothing is written or read.
CASE_INVALID = "CASE_INVALID"

CAUSES = frozenset({CASE_CONFLICT, CASE_TAMPERED, CASE_INVALID})


class CorpusRefused(ValueError):
    """A bank or a read refused with a named cause; nothing was written or read."""

    def __init__(self, message: str, cause: str) -> None:
        super().__init__(message)
        self.cause = cause