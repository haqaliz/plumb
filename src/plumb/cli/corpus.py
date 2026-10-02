"""`plumb corpus` — the discrepancy-corpus surface: bank a verify record as a case.

`bank_record` is the bank seam: the record is validated by the **replay chain**
(`read_record` — strict member reading, run-id check, curated claims re-admitted
against the record's own paper — then `load_bindings` + `verify_claims`
re-derivation from the stored trace, then `cross_check` against the committed
`verdicts.json`), exactly as `plumb verify --from-record` reads it. A record
that would not replay does not bank: nothing is written on any refusal. The
committed `verdicts.json` is never trusted alone — the bank re-derives first
and cross-checks.

**The bank transports, never creates.** The optional record-side `labels.json`
(human-authored) is validated against the re-admitted claim ids and transported
into the case; a malformed one is `RECORD_INVALID`. The record's
`unrepresentable.json` (the gate record's non-claim document) is staged as the
case's `nonclaims.json` **verbatim**. No labels file, no `unrepresentable.json`
→ no `labels.json`, no `nonclaims` lane.

**Staging is transient.** The lanes are copied into a `tempfile` directory
exactly as `bank_case` reads a record, so the case bytes derive from the
record's bytes only — the temp path never reaches the case. The case id is
content-addressed; a re-bank of the identical record is a no-op, a conflicting
re-bank is `CorpusRefused` (`CASE_CONFLICT`), and the existing case is never
touched.

**The report reads the store back.** `cmd_corpus_report` implements
`plumb corpus report [--store DIR] [--authority owner|third-party] [--json]`:
every `<case_id>/` directory carrying a `case.json` manifest is a case
(anything else is not a case), each case is read through the store's
hash-verified path — a tampered or unreadable case refuses the whole report
with `CorpusRefused` naming the case, never a silent drop — and the metrics
are computed over the verdicts and verified labels. The label authority is a
reporting-time declaration, carried next to every precision/recall figure.
The table is fixed-layout and deterministic: per-case rows (case_id, claims,
bound, by-verdict counts, labeled `DIVERGED`s, confirmed) and a totals row,
then coverage and the two rates with their denominators, `n/n (authority)` —
or `no labeled DIVERGEDs` / `no labeled claims` when no such figure exists.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile

from plumb.cli.replay import cross_check, read_record
from plumb.corpus import bank_case, read_case
from plumb.corpus.causes import CASE_INVALID, CorpusRefused
from plumb.corpus.metrics import (
    DIVERGED,
    REPRODUCED,
    UNVERIFIED,
    WITHIN_TOLERANCE,
    CaseMetrics,
    Metrics,
    Rate,
    Totals,
    read_verdict_rows,
    serialize_metrics,
    store_metrics,
)
from plumb.verify import Completed, load_bindings, verify_claims

__all__ = ["bank_for_verify", "bank_record", "cmd_corpus_bank", "cmd_corpus_report"]

#: The label values a human-authored review may carry; anything else is malformed.
_LABEL_VALUES = frozenset({"confirmed", "refuted"})

#: The default store: the same `corpus bank`/`corpus report` default (cli/__init__.py).
DEFAULT_STORE = "corpus/local"

#: The member lanes `bank_case` reads of a record, in the order the record carries them.
_MEMBER_FILES = ("claims.json", "bindings.json", "trace.json", "verdicts.json")

_PAPER_FILES = ("paper.pdf", "paper.md")


def cmd_corpus_bank(args, parser) -> int:
    """`plumb corpus bank <record-dir> [--store DIR]`: bank, print, exit 0."""
    record_dir = Path(args.record_dir)
    if not record_dir.is_dir():
        parser.error(f"<record-dir> {args.record_dir!r} is not a directory")
    case_id, already = bank_record(record_dir, Path(args.store))
    print(f"already banked: {case_id}" if already else f"banked {case_id}")
    return 0


def bank_for_verify(record_dir: Path) -> bool:
    """Bank `record_dir` into the default store, shell-style; return whether it banked.

    The verify shell's two modes call this after the verdicts have rendered:
    success prints `banked <case_id>` (or `already banked: <case_id>`) on
    stdout; a refusal prints one named-cause line on stderr — `CORPUS_REFUSED`
    for a store that refuses, `RECORD_INVALID` for a record that does not
    replay — and returns False. The verdicts have already rendered; this is
    the bank's own outcome.
    """
    from plumb.cli import CORPUS_REFUSED, RECORD_INVALID

    try:
        case_id, already = bank_record(record_dir, Path(DEFAULT_STORE))
    except CorpusRefused as exc:
        print(f"plumb verify: {CORPUS_REFUSED}: {exc}", file=sys.stderr)
        return False
    except ValueError as exc:
        print(f"plumb verify: {RECORD_INVALID}: {exc}", file=sys.stderr)
        return False
    print(f"already banked: {case_id}" if already else f"banked {case_id}")
    return True


def bank_record(record_dir: Path, store_dir: Path) -> tuple[str, bool]:
    """Bank `record_dir` under `store_dir`; returns `(case_id, was_a_no_op)`.

    The record is validated by the replay chain before anything is written;
    `labels` are read record-side and validated; the lanes are staged in a
    transient directory and banked through `bank_case`. Nothing is banked on
    any refusal.
    """
    claims, bindings_bytes, trace, capture, _paper, _paper_format = read_record(record_dir)
    bindings = load_bindings(bindings_bytes, [c.id for c in claims])
    verdicts = verify_claims(claims, bindings, Completed(trace, capture))
    cross_check(record_dir, verdicts)
    labels = _record_labels(record_dir, {c.id for c in claims})
    with tempfile.TemporaryDirectory(prefix="plumb-corpus-") as tmp:
        staged = _stage(record_dir, Path(tmp) / "record")
        with tempfile.TemporaryDirectory(prefix="plumb-corpus-probe-") as probe:
            case = bank_case(staged, probe, labels=labels)
        already = (store_dir / case.case_id).exists()
        bank_case(staged, store_dir, labels=labels)
    return case.case_id, already


def _record_labels(record_dir: Path, claim_ids: set[str]) -> dict[str, str] | None:
    """The record's human-authored labels, validated against the re-admitted ids.

    Absent `labels.json` -> `None`: the bank transports, never creates. A
    document that is not an object, a key that is not a re-admitted claim id,
    or a value outside `{confirmed, refuted}` is `ValueError`, which the shell
    renders as `RECORD_INVALID`.
    """
    path = record_dir / "labels.json"
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"record {record_dir}: labels.json does not parse: {exc!r}"
        ) from None
    if not isinstance(document, dict):
        raise ValueError(f"record {record_dir}: labels.json must be an object")
    for claim_id, value in document.items():
        if claim_id not in claim_ids:
            raise ValueError(
                f"record {record_dir}: labels.json names unknown claim {claim_id!r}"
            )
        if value not in _LABEL_VALUES:
            raise ValueError(
                f"record {record_dir}: the label for {claim_id!r} must be one of "
                "confirmed, refuted"
            )
    return dict(document)


def _stage(record_dir: Path, staged: Path) -> Path:
    """The record's lanes under `staged`, exactly what `bank_case` reads.

    The member files, the `objects/` tree and the paper (pdf preferred, else
    markdown) are copied verbatim; the record's `unrepresentable.json`, when
    present, is written as the case's `nonclaims.json` verbatim.
    """
    staged.mkdir(parents=True)
    for name in _MEMBER_FILES:
        shutil.copyfile(record_dir / name, staged / name)
    shutil.copytree(record_dir / "objects", staged / "objects")
    for name in _PAPER_FILES:
        path = record_dir / name
        if path.is_file():
            shutil.copyfile(path, staged / name)
            break
    unrepresentable = record_dir / "unrepresentable.json"
    if unrepresentable.is_file():
        (staged / "nonclaims.json").write_bytes(unrepresentable.read_bytes())
    return staged


def cmd_corpus_report(args, parser) -> int:
    """`plumb corpus report [--store DIR] [--authority ...] [--json]`: report, exit 0.

    Every `<case_id>/` subdirectory of the store that carries a `case.json`
    manifest is a case, read through the store's hash-verified path in sorted
    `case_id` order. A missing store directory, a tampered member, or a case
    that does not read back is `CorpusRefused` — the report is all or nothing,
    never a silent skip.
    """
    store_dir = Path(args.store)
    if not store_dir.is_dir():
        raise CorpusRefused(f"store {store_dir} is not a directory", CASE_INVALID)
    cases = [
        read_case(entry)
        for entry in sorted(store_dir.iterdir())
        if entry.is_dir() and (entry / "case.json").is_file()
    ]
    for case in cases:
        try:
            read_verdict_rows(case.members["verdicts"])
        except ValueError as exc:
            raise CorpusRefused(
                f"case {case.case.case_id}: {exc}", CASE_INVALID
            ) from None
    try:
        metrics = store_metrics(cases)
    except ValueError as exc:
        raise CorpusRefused(str(exc), CASE_INVALID) from None
    if args.json:
        sys.stdout.buffer.write(serialize_metrics(metrics, args.authority))
    else:
        sys.stdout.buffer.write(_render_report_table(metrics, args.authority))
    sys.stdout.buffer.flush()
    return 0


#: The fixed column layout of the report table: header label and cell width.
_COLUMNS = (
    ("CASE", 24),
    ("CLAIMS", 6),
    ("BOUND", 5),
    ("REPRODUCED", 10),
    ("WITHIN-TOLERANCE", 16),
    ("DIVERGED", 8),
    ("UNVERIFIED", 10),
    ("LABELED", 7),
    ("CONFIRMED", 9),
)

#: The by-verdict cells, in the metrics' pinned C4 order, with their widths.
_VERDICT_WIDTHS = ((REPRODUCED, 10), (WITHIN_TOLERANCE, 16), (DIVERGED, 8), (UNVERIFIED, 10))

_TRUNCATE = 24
_ELLIPSIS = "…"


def _render_report_table(metrics: Metrics, authority: str) -> bytes:
    """The report as a fixed-layout table: header, per-case rows, totals, rates.

    Every row is one line; nothing from the machine (no clock, no cwd) enters
    the bytes. The `LABELED` column counts the case's labeled `DIVERGED`s
    (confirmed + refuted); `CONFIRMED` is the confirmed subset. Below the
    totals row, coverage and the two rates carry their denominators, and the
    label-authority declaration is rendered next to every figure.
    """
    lines = [_header(), _separator()]
    lines.extend(_case_row(case_metrics) for case_metrics in metrics.cases)
    lines.append(_totals_row(metrics.totals))
    lines.append("")
    lines.append(_rate_lines(metrics.totals, authority))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _header() -> str:
    return " | ".join(name.ljust(width) for name, width in _COLUMNS)


def _separator() -> str:
    width = sum(width for _, width in _COLUMNS) + 3 * (len(_COLUMNS) - 1)
    return "-" * width


def _case_row(case_metrics: CaseMetrics) -> str:
    coverage = case_metrics.coverage
    cells = [
        (_truncate(case_metrics.case_id), 24),
        (str(coverage.claims), 6),
        (str(coverage.bound), 5),
    ]
    cells.extend(
        (str(count), width)
        for (_, count), (_, width) in zip(coverage.by_verdict, _VERDICT_WIDTHS)
    )
    cells.extend(
        (
            (str(case_metrics.confirmed + case_metrics.refuted), 7),
            (str(case_metrics.confirmed), 9),
        )
    )
    return _render_row(cells)


def _totals_row(totals: Totals) -> str:
    noun = "case" if totals.cases == 1 else "cases"
    coverage = totals.coverage
    cells = [
        (f"total ({totals.cases} {noun})", 24),
        (str(coverage.claims), 6),
        (str(coverage.bound), 5),
    ]
    cells.extend(
        (str(count), width)
        for (_, count), (_, width) in zip(coverage.by_verdict, _VERDICT_WIDTHS)
    )
    cells.extend(
        (
            (str(totals.confirmed + totals.refuted), 7),
            (str(totals.confirmed), 9),
        )
    )
    return _render_row(cells)


def _render_row(cells: list[tuple[str, int]]) -> str:
    return " | ".join(text.ljust(width) for text, width in cells)


def _rate_lines(totals: Totals, authority: str) -> str:
    """Coverage and the two rates, every figure with its denominator."""
    lines = [f"  coverage: {totals.coverage.bound}/{totals.coverage.claims} bound"]
    lines.append(_rate_line("precision", totals.precision, authority, "no labeled DIVERGEDs"))
    lines.append(_rate_line("recall", totals.recall, authority, "no labeled claims"))
    return "\n".join(lines)


def _rate_line(kind: str, rate: Rate | None, authority: str, none_text: str) -> str:
    if rate is None:
        return f"  {kind}: {none_text}"
    return f"  {kind}: {rate.confirmed}/{rate.flagged} ({authority})"


def _truncate(text: str) -> str:
    """Truncate to `_TRUNCATE` code points, ending in `…` when anything was cut."""
    if len(text) <= _TRUNCATE:
        return text
    return text[: _TRUNCATE - 1] + _ELLIPSIS