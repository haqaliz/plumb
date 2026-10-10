"""The verdict set's two renderings: canonical JSON, or the fixed-layout human table.

`render_verdicts(verdict_set, *, json: bool) -> bytes` is the seam the CLI shell
composes (`src/plumb/cli/__init__.py`). It is pure: a `VerdictSet` in, bytes out, no
exit code, no stdout — the shell decides exits and writes bytes. Both renderings are
byte-identical across invocations, in one process and across processes under any
`PYTHONHASHSEED` (pinned by `tests/cli/test_render_determinism.py`).

**`--json`** is the engine's canonical document, and it is literally
`serialize_verdicts`'s: the field names, Decimal-as-exact-text, `review_required`,
`sort_keys`/`separators`/`allow_nan`, UTF-8 without escapes, and the one trailing
newline are all the record contract's own, not a CLI re-spelling that could drift. A
byte-identical reimplementation here would be a second door to the same bytes — so
there is none.

**The table** is fixed-width by construction: seven columns
(`VERDICT | CAUSE | CLAIM ID | REPORTED | REDERIVED | ARTIFACT | LOCATOR`), each cell
left-aligned to a pinned width, any text longer than 24 code points truncated to
23 + `…` (slicing by code point, so a multi-byte UTF-8 character is never split),
and newlines inside a cell replaced with `␤` so one verdict is always one line. The
rows come in `VerdictSet`'s own order (sorted by claim id). Below the separator a
summary block reports coverage: `claims`/`bound`, the four verdict totals in the fixed
order REPRODUCED, WITHIN-TOLERANCE, DIVERGED, UNVERIFIED, and `by cause` sorted
alphabetically.

**Nothing from the user's machine.** No clock, no working directory, no environment,
no locale-sensitive call, no randomness — determinism comes from not having sources of
nondeterminism, exactly as in `plumb.verify.serialize` and `plumb.extract.serialize`.
"""

from __future__ import annotations

from plumb.verify.bindings import CsvCell, JsonPointer, NotebookCell, StdoutRegex
from plumb.verify.serialize import serialize_verdicts
from plumb.verify.verdict import Verdict, VerdictSet

__all__ = ["render_verdicts"]

#: The fixed column layout: header label and cell width, in order.
_COLUMNS = (
    ("VERDICT", 15),
    ("CAUSE", 24),
    ("CLAIM ID", 24),
    ("REPORTED", 24),
    ("REDERIVED", 24),
    ("ARTIFACT", 24),
    ("LOCATOR", 24),
)

#: Text longer than this is truncated to `width - 1` code points plus the ellipsis.
_TRUNCATE = 24
_ELLIPSIS = "…"
_NEWLINE = "␤"


def render_verdicts(verdict_set: VerdictSet, *, json: bool) -> bytes:
    """The verdict set as canonical JSON (`json=True`) or the fixed-layout table."""
    if json:
        return _render_json(verdict_set)
    return _render_table(verdict_set)


def _render_json(verdict_set: VerdictSet) -> bytes:
    """The canonical document — `serialize_verdicts`'s bytes, unchanged."""
    return serialize_verdicts(verdict_set)


def _render_table(verdict_set: VerdictSet) -> bytes:
    """Header, separator, one row per claim, then the summary block."""
    lines = [_header(), _separator()]
    lines.extend(_row(v) for v in verdict_set.verdicts)
    lines.append("")
    lines.append(_render_summary(verdict_set))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _header() -> str:
    return " | ".join(name.ljust(width) for name, width in _COLUMNS)


def _separator() -> str:
    width = sum(width for _, width in _COLUMNS) + 3 * (len(_COLUMNS) - 1)
    return "-" * width


def _row(verdict: Verdict) -> str:
    cells = (
        (verdict.verdict, 15),
        ("" if verdict.cause is None else verdict.cause, 24),
        (verdict.claim_id, 24),
        (verdict.reported_text, 24),
        ("" if verdict.rederived is None else str(verdict.rederived), 24),
        ("" if verdict.artifact is None else verdict.artifact, 24),
        (_locator_text(verdict), 24),
    )
    return " | ".join(_cell(text, width) for text, width in cells)


def _cell(text: str, width: int) -> str:
    """One table cell: sanitized, truncated to `width`, left-aligned to `width`."""
    return _truncate(_sanitize(text), width).ljust(width)


def _sanitize(text: str) -> str:
    """Newlines become `␤` so a verdict with a multi-line located value stays one line."""
    return text.replace("\r\n", _NEWLINE).replace("\n", _NEWLINE).replace("\r", _NEWLINE)


def _truncate(text: str, width: int) -> str:
    """Truncate to `width` code points, ending in `…` when anything was cut.

    Slicing operates on code points, never on bytes, so a multi-byte UTF-8 character
    (µ, →, ␤, …) is kept whole or dropped whole — never split in half.
    """
    if len(text) <= width:
        return text
    return text[: width - 1] + _ELLIPSIS


def _locator_text(verdict: Verdict) -> str:
    """Where the value came from, and (when bound) the raw text that was located."""
    locator = verdict.locator
    if isinstance(locator, JsonPointer):
        text = f"json: {locator.pointer}"
    elif isinstance(locator, NotebookCell):
        cell = verdict.artifact.rsplit("#", 1)[-1]
        if locator.table is not None:
            text = f"{cell} r{locator.table.row}c{locator.table.column} {locator.pointer}"
        else:
            text = f"{cell} {locator.pointer}"
    elif isinstance(locator, StdoutRegex):
        text = f"stdout: {locator.pattern}"
    elif isinstance(locator, CsvCell):
        selectors = ", ".join(
            value if key == "" else f"{key}={value}" for key, value in sorted(locator.row)
        )
        text = f"csv: {locator.column}[{selectors}]"
    else:
        return ""
    if verdict.located_text is not None:
        text += f" → {verdict.located_text}"
    return text


def _render_summary(verdict_set: VerdictSet) -> str:
    """The summary block: coverage, verdict totals, and causes — all deterministic.

    `coverage["by_verdict"]` is already ordered REPRODUCED, WITHIN-TOLERANCE, DIVERGED,
    UNVERIFIED and `coverage["by_cause"]` already alphabetical (`plumb.verify.verdict`),
    so the block is a fixed-order rendering of counts the record itself derives.
    """
    coverage = verdict_set.coverage
    lines = [
        "Summary",
        f"  claims: {coverage['claims']}  bound: {coverage['bound']}",
        "  " + "  ".join(f"{kind}: {count}" for kind, count in coverage["by_verdict"].items()),
    ]
    causes = coverage["by_cause"]
    if causes:
        lines.append("  by cause:")
        lines.extend(f"    {cause}: {count}" for cause, count in causes.items())
    else:
        lines.append("  by cause: (none)")
    return "\n".join(lines)