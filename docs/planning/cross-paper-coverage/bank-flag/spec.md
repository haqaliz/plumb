# Spec — bank-flag (cross-paper-coverage, aspect 1)

Source: `docs/planning/cross-paper-coverage/prd.md` R1–R3, N1 (approved 2026-10-02).

## Problem slice

Close the verify→bank loop: a live `plumb verify` run persists its record dir and banks
it through the existing corpus replay chain, so the corpus can accrue without
hand-assembly (`docs/planning/_card/issue.md:11-16`). This is the enabling slice for the
panel campaign (`panel-run` aspect) and the R1 number (`r1-report` aspect).

## In scope

- **R2 — Dual-form claims read.** `read_record` (`src/plumb/cli/replay.py:96-124`)
  accepts the C1 record form (`serialize_claims`, `src/plumb/extract/serialize.py:300`):
  document shape `{"claims", "paper_hash"}` → `parse_claims` + paper-hash check against
  the record's own paper + `readmit` through the admission gate (the bundle path's read,
  `src/plumb/bundle/verify.py:185-191`). Curated form (`{"claims"}`) unchanged.
- **R1 — Live record writer.** New `src/plumb/cli/record.py::write_record` assembles a
  record dir from live-spine materials (`src/plumb/cli/live.py:153` in hand): C1-form
  `claims.json`, raw `bindings.json` bytes, `serialize_trace` output, `objects/` —
  **locatable artifacts only** (`capture.locatable`; stderr `diagnostic_only` excluded,
  `src/plumb/run/capture.py:51-59, 83`), `paper.pdf|md` (the run's own bytes), and
  `verdicts.json` (`serialize_verdicts`). Written to a temp/scratch dir, never the
  pinned checkout.
- **R3 — `--bank` flag.** On `plumb verify`, valid in live and `--from-record` modes;
  banks into the default store `corpus/local` (the corpus commands' default,
  `src/plumb/cli/__init__.py:260-261`) through `bank_record` (`src/plumb/cli/corpus.py:87-106`)
  — replay-chain validation, write-once/no-op from `bank_case`. Verdicts render
  regardless; a bank refusal is `CORPUS_REFUSED` (or `RECORD_INVALID`), exit 1; the case
  id is printed; the record is discarded after banking. **Failed/stubbed runs bank
  too**: `WONT_RUN`/`NO_ARTIFACT`/stub-env runs produce all-`UNVERIFIED` cases with the
  run-level cause in the trace — the honest default, never a refusal. A run that never
  started (`ENTRYPOINT_MISSING`/`_AMBIGUOUS`, `NoRun`) has no trace to write a record
  from and banks nothing — silent, not a refusal.
- **N1 — `--out`-ready records** (optional final phase): the writer also emits
  `environment.txt` + `source.json` (the six `SourceRecord` fields,
  `replay.py:65-67`), so live records support `--from-record --out` rebuilds.

## Out of scope

- `--store` flag on `verify` (default store only; tests redirect via
  `monkeypatch.chdir(tmp_path)`); nonclaims lane on live runs (N2 stays fixture-only);
  `--timeout-seconds`/`--run-dir` knobs; the panel campaign (`panel-run`); the R1 number
  and `docs/ROADMAP.md` update (`r1-report`).

## Acceptance criteria (the failing tests, written first)

1. A synthetic live run with `--bank` (`--no-env-build`, fixture repo) exits 0, writes
   the case under the default store, prints its id; re-banking (via `corpus bank --store
   <same>`) is a no-op.
2. A record written by `write_record` (real run materials) replays through
   `--from-record --json` byte-identical to its `verdicts.json`; its banked case's
   `objects/` are exactly `capture.locatable` (no stderr, no local paths).
3. Dual-form read: the C1-form record from (2) replays; the curated AgroDesign record
   replays unchanged (existing `tests/cli/test_replay.py` and `tests/gate/` do not move);
   a C1-form record whose `paper_hash` mismatches its paper, and a document with any
   other shape, are `RECORD_INVALID`.
4. `--from-record --bank` on the AgroDesign fixture (tmp store) banks case #2's peer —
   the same case `corpus bank` produces; a second run is the no-op.
5. A run that produces no capturable output (`NO_ARTIFACT`) with `--bank` exits 1 and
   the case banks with all `UNVERIFIED` verdicts and the run-level cause in the trace.
6. A bank refusal on the live path (store path is a regular file) exits 1 with
   `CORPUS_REFUSED` on stderr and the verdicts still rendered on stdout.
7. Determinism: two `--bank` invocations in one process (varied `PYTHONHASHSEED`)
   produce byte-identical stdout; `corpus report --json --store <tmp>` over the
   AgroDesign case + a live case pools 2 rows with denominators and `authority`
   markers. (Two *different* live runs bank two distinct cases: trace bytes carry
   wall-clock mtimes, so byte-dedup holds within a record, not across runs — a
   re-bank of identical bytes is the no-op.)
8. No network: the suite passes under the autouse blocker (`tests/conftest.py:56-60`);
   real env builds never run in tests (the stub is the only tested path).

## Dependencies and sequencing

Depends on C4/C5's built seams only. Order: dual-form read (R2) → writer (R1) → `--bank`
(R3) → determinism/pooled report → optional N1. Each phase keeps the suite green
(`uv run pytest`); commits per phase on `feat/cross-paper-coverage/aliz`.

## Open questions

- None blocking. `--bank` with `--out` together is allowed (bank + bundle both written);
  `--bank` without a store override is the only surface (per the approved PRD).