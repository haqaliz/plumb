# Spec — notebook-paper / fixture

One aspect: the whole unit (paper fixture + campaign), planned in `plan_20261010.md`. PRD:
`docs/planning/notebook-paper/prd.md` (P1–P5, P2a). Understanding (panel screen + probe):
`understanding.md` in the parent directory.

## Problem slice

Put the notebook_cell locator to work on a real paper: fixture arXiv:2609.00137
(notebook-only repo, deterministic), bind rule-encoded claims through `notebook_cell`
locators, run it for real at dev time, commit the record, bank it, and report denominators
and owner labels.

## In scope

- `fixtures/gate/rcai/`: paper member (arXiv PDF; HTML fallback per P2a), provenance README
  (URLs, licenses, SHA-256 pins, the selection rule verbatim, runtime measurement), claims
  (C1 form), bindings (notebook_cell pointers), trace, objects, verdicts, environment +
  source records.
- `tools/rcai_spec.py` (rule-encoded claims + bindings; exactly-once `unique_offset` spans),
  `tools/rcai_run.py` (dev-time: resolve → env build → notebook run → verify → write record
  → bank).
- Offline tests: fixture grounding, verbatim spans, distinct ids, C1 conformance floor, PDF
  seam on this paper, byte-identical replay, no-local-path scan, bank/report pooling.
- Anti-inflation: the claims rule is committed before the dev-time run; bindings committed
  before the run; the pre-registered float_repr/written-precision reading per claim.

## Out of scope

Engine changes (locators, causes, comparison — shipped in PR #15); candidates 2–3 (Erwin,
Patel — screened, backlogged); publishing duties (R4).

## Acceptance criteria (testable, offline)

1. `--from-record --json` equals the record's `verdicts.json`, byte for byte, on the
   committed `fixtures/gate/rcai/` record.
2. ≥1 claim's verdict flows through a `notebook_cell` locator; the located value was read by
   hash from a fresh cell artifact of the dev-time run — a stale/committed notebook is never
   read (constraint #5); the record's `objects/` hold only locatable bytes.
3. The rule-encoded claims are grounded verbatim at their spans (test); C1 recovery on this
   paper is reported as conformance with its own count.
4. `corpus bank|report` pools the case with denominators and the owner-authority marker;
   every `DIVERGED` is owner-labeled.
5. No local paths in committed evidence; byte-identical across invocations
   (PYTHONHASHSEED-varied); full suite green and network-free; the 5 seated PDF fixtures'
   recovery floors do not move.

## Dependencies / sequencing

P1 paper+converter → P2 claims rule (pre-run) → P3 bindings (pre-run) → P4 dev-time run
(tools/, supervised, authorized fetch) → P5 offline suite + labels + report. The dev-time
run is the only network-touching step and never runs in CI.