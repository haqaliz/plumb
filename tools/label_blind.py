#!/usr/bin/env python3
"""Interactive blind-labelling runner for the C1 claim-selection fixture set.

Reads the emitted `.todo.jsonl` files under `fixtures/labels/`, walks every
unanswered row one at a time, and records the human's claim / not-claim verdict.
The labels are the measurement instrument for the selection rule (M15): the rule
must be scored against labels it did not author, so this script never suggests a
label, never skips a row, and saves progress after every answer so an interrupted
pass loses nothing.

Usage:
    uv run tools/label_blind.py            # walk unanswered rows
    uv run tools/label_blind.py --check    # verify label files only, then exit

Answers: y = claim, n = not-claim, ? = help, q = quit (progress is saved).
Rows already answered in a previous run are skipped on resume.

The written files are byte-identical to the emitter's format
(`labelling.py` `_JSON`: `ensure_ascii=False`, separators `(", ", ": ")`, key
order `ROW_FIELDS`) and only the `label` field ever differs from the file's state
at the start of the run.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABELS_DIR = ROOT / "fixtures" / "labels"
JSON_OPTS = {"ensure_ascii": False, "separators": (", ", ": ")}

CLAIM = "claim"
NOT_CLAIM = "not-claim"


def load_files() -> list[tuple[Path, dict, list[dict]]]:
    files = []
    for path in sorted(LABELS_DIR.glob("*.todo.jsonl")):
        lines = path.read_text(encoding="utf-8").splitlines()
        header = json.loads(lines[0])
        rows = [json.loads(line) for line in lines[1:]]
        files.append((path, header, rows))
        print(f"{path.name}: {len(rows)} rows, "
              f"{sum(1 for r in rows if r['label'] is not None)} answered")
    return files


def write_file(path: Path, header: dict, rows: list[dict]) -> None:
    """Rewrite one label file atomically, preserving the emitter's format."""
    payload = "\n".join(
        [json.dumps(header, **JSON_OPTS)]
        + [json.dumps(row, **JSON_OPTS) for row in rows]
    ) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def snapshot(rows: list[dict]) -> list[dict]:
    return [dict(r) for r in rows]


def verify_unchanged(rows: list[dict], before: list[dict]) -> bool:
    """Only the label field may differ from the state at run start."""
    ok = True
    for row, prior in zip(rows, before):
        for field, value in prior.items():
            if field == "label":
                continue
            if row.get(field) != value:
                print(f"  ERROR: field {field!r} changed on row {row['id']}")
                ok = False
    return ok


def run_pass() -> None:
    files = load_files()
    total = sum(len(rows) for _, _, rows in files)
    answered = sum(1 for _, _, rows in files for r in rows if r["label"] is not None)
    print(f"\n{answered}/{total} rows answered. Walking the rest.")

    done = 0
    for path, header, rows in files:
        before = snapshot(rows)
        for row in rows:
            if row["label"] is not None:
                continue
            done += 1
            print("\n" + "=" * 72)
            print(f"[{answered + done}/{total}] {row['document']} "
                  f"(section: {row['section']}) — {row['id']}")
            print(f"  value:   {row['text']!r}")
            print(f"  context: {row['context_before']}|{row['text']}|{row['context_after']}")
            while True:
                answer = input("  claim? [y/n] (?=help q=quit) > ").strip().lower()
                if answer in ("y", "yes"):
                    row["label"] = CLAIM
                    break
                if answer in ("n", "no"):
                    row["label"] = NOT_CLAIM
                    break
                if answer == "?":
                    print(
                        "  YES (y) — the paper asserts this number as ONE OF ITS OWN\n"
                        "            quantitative results: a named metric with a value\n"
                        "            (prevalence 0.8%, AUC 0.84, p < 0.001, R2 of 0.23,\n"
                        "            a 95% CI, a 6.7x speedup).\n"
                        "  NO  (n) — anything else:\n"
                        "            * sample sizes / N (n = 6630, 120 participants)\n"
                        "            * years (2004, 2025), DOIs, grant numbers, ORCIDs\n"
                        "            * measurement identifiers (A2, A28, R2's superscript 2)\n"
                        "            * count-of-measurements metadata (22 linear, 6 angular)\n"
                        "            * '2' inside 'type 2 diabetes'\n"
                        "            * values in brackets that are citations [1], [30,31]\n"
                        "  q = quit now — progress is saved after every answer"
                    )
                    continue
                if answer == "q":
                    if verify_unchanged(rows, before):
                        write_file(path, header, rows)
                    print(f"\nQuit. Progress saved ({answered + done - 1}/{total}).")
                    sys.exit(0)
                print("  enter y or n (or ? for help, q to quit)")
            write_file(path, header, rows)
        if not verify_unchanged(rows, before):
            sys.exit("Aborting: a non-label field was modified — nothing written.")

    counts: dict[str, dict[str, int]] = {}
    for path, header, rows in files:
        claims = sum(1 for r in rows if r["label"] == CLAIM)
        counts[path.name] = {"claim": claims, "not-claim": len(rows) - claims}
    print("\n" + "=" * 72)
    print(f"All {total} rows answered.")
    for name, c in counts.items():
        print(f"  {name}: {c['claim']} claim, {c['not-claim']} not-claim")
    print("\nLabels saved. Tell the integrator the pass is done.")


def run_check() -> None:
    files = load_files()
    bad = 0
    for path, header, rows in files:
        for row in rows:
            if row["label"] is None:
                print(f"  UNANSWERED: {row['document']} {row['id']} {row['text']!r}")
                bad += 1
            elif row["label"] not in (CLAIM, NOT_CLAIM):
                print(f"  BAD LABEL {row['label']!r}: {row['document']} {row['id']}")
                bad += 1
    if bad:
        sys.exit(f"{bad} row(s) need attention.")
    print("Check passed: every row answered with a valid label.")


if __name__ == "__main__":
    if "--check" in sys.argv:
        run_check()
    else:
        run_pass()