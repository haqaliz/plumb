# capture — aspect spec (`notebook-capture`)

Problem slice: PRD M3–M6. `capture_outputs` learns `.ipynb`: every **fresh** notebook is
stored whole-file (`kind="notebook"`, raw bytes), and each output-bearing cell additionally
becomes a content-addressed `notebook_cell` artifact at `<relpath>#cell-<i>`, freshness-guarded
by the notebook file's mtime. The `RunTrace` schema is untouched — these are ordinary
`Artifact` records.

## In scope

- Extend the capture walk to include `.ipynb` alongside `.json`/`.csv` (recursive, symlinks
  not followed, same as today).
- Whole-file artifact: `kind="notebook"`, `relpath` the file's POSIX relpath, `sha256` over
  the raw file bytes, size, mtime.
- Per-cell artifacts: for each cell whose `outputs` is a non-empty list and can be
  canonicalized, `kind="notebook_cell"`, `relpath=f"{relpath}#cell-{i}"` with `i` the 0-based
  index into the notebook's `cells` array; bytes = canonical JSON of the `outputs` array
  (sorted keys, compact separators, UTF-8, one trailing newline), matching the house
  canonical form (`src/plumb/run/trace.py:42-47,97-99`).
- Undecomposable fresh notebook (bad JSON, missing/non-list `cells`, non-dict cell, non-list
  outputs, or a projection that cannot serialize, e.g. `NaN`/`Infinity` with
  `allow_nan=False`): whole-file artifact only, zero cell artifacts, no exception, no new
  cause.
- Freshness guard applies to the file: stale → one `StaleOutput` (relpath, mtime, size),
  bytes never read, zero artifacts from it. Boundary strict `<` (mtime == start is fresh).
- Docstrings in `src/plumb/run/capture.py` (module, `Artifact.kind` vocabulary) updated.

## Out of scope

- Any trace change (`trace.py` untouched); replay round-trip and CLI e2e are the `spine`
  aspect.
- The C4 `notebook_cell` locator and binding schema.
- `NO_ARTIFACT` semantics changes: a fresh notebook with no outputs is still a captured
  file (its mtime-counting keeps the run non-silent), exactly like an empty `.json`.

## Acceptance criteria (testable, written failing first — all offline, `tests/run/test_capture.py`)

1. A fresh notebook in the working copy yields one `notebook` artifact whose `Capture.read`
   returns the exact raw bytes and whose sha256 matches them; a tampered store still raises.
2. Per output-bearing cell: a `notebook_cell` artifact at `<relpath>#cell-<i>` with the
   canonical projection bytes; a markdown cell and a code cell with empty `outputs`
   contribute nothing; cell indices are positions in the `cells` array.
3. Undecomposable notebooks (bad JSON bytes; `cells` not a list; a `NaN` literal inside an
   output) yield the whole-file artifact and zero cell artifacts, with no exception.
4. A stale notebook (`mtime < started_at_ns`) is a `StaleOutput`; its bytes are never stored
   (no artifact, sha absent from the store); the boundary test still holds (`==` fresh,
   `start-1ns` stale); a committed untouched notebook is stale; a run-rewritten one is fresh.
5. Two fresh notebooks in one run are both captured; artifacts sort deterministically as
   today; symlinked notebooks are skipped.
6. Full suite green; no new runtime deps; no new causes; `run/trace.py` unchanged.

## Dependencies and sequencing

None (independent of `entrypoint`, which landed first). C1 (whole-file + freshness) →
C2 (per-cell decomposition). `spine` depends on both.

## Open questions / risks

- A notebook with large base64 outputs stores one object per cell — accepted for the first
  slice; a size cap is a named follow-on.
- `execution_count` is deliberately not projected (a cell field, not an output), so cell
  hashes are stable across re-executions with identical outputs.
