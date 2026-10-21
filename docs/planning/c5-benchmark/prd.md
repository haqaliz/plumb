# PRD — publish the C5 precision/recall benchmark

Issue: #22. Closes the "stays Phase 2" line in the C5 status.

## Requirements

- **R1** — `tools/benchmark.py` banks the three committed gate records into a temp store and
  writes `docs/benchmark/REPORT.md`.
- **R2** — `--check` rebuilds and exits 1 when the committed file is stale; a test runs it, so
  CI catches drift.
- **R3** — the report carries: the panel, the case ids (full), the fixed-layout table,
  coverage with its denominator, precision/recall with denominators and label authority, the
  confirmed/refuted accounting, and a "what this number is not" section.
- **R4** — `docs/METHOD.md` and the C5 status link to it; no hand-maintained number.

## Non-goals

- Adding papers to the panel (needs runnable cases; #23 widens the no-code path instead).
- Third-party labels.

## Acceptance

`tests/test_benchmark_report.py` (current + the number with denominators), full suite green.
