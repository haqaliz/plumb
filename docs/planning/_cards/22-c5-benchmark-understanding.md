# Understanding — publish the C5 benchmark (#22)

## What the work really is

The math and the store already exist (`src/plumb/corpus/metrics.py`, `plumb corpus report`).
What is missing is a **published artifact that cannot silently drift from the data**: the panel
lives in `corpus/local/` (gitignored), so the only reproducible source is the three committed
gate records under `fixtures/gate/`.

The lazy complete change is therefore a generator plus a golden test: bank the committed records
into a transient store, compute with the same `store_metrics`/`_render_report_table` the CLI
uses, write `docs/benchmark/REPORT.md`, and fail a test when the committed file differs from a
fresh build.

## Decisions

- **No new engine code.** Reusing `bank_record` and the report renderer means the published
  number cannot disagree with `plumb corpus report`.
- **The case ids are listed**, because the report table truncates them and a reader needs the
  full id to reproduce or cite a case.
- **The refuted accounting is stated in prose from the metrics**, not typed: `14 refuted, 1
  confirmed` is derived from `totals`, so growing the corpus moves it automatically.
- **Growing the corpus is out of scope** on purpose: the panel is selected by a fixed rule, and
  padding it with papers that do not run would be dishonest. #23 (C7) widens *coverage* of
  papers, not the panel.

## Pipeline placement

C5 (corpus/benchmark). Reporting only; no verdict logic.
