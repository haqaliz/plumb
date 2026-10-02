# Understanding — cross-paper-coverage (C5, next slice)

Source: `docs/planning/_card/issue.md` (pbf handoff brief, 2026-10-02). Dig agents mapped
the CLI/bank seams and the fixture/tooling conventions on 2026-10-02.

## What the work is really asking

Measure R1 — cross-paper binding coverage (`docs/ROADMAP.md:41-45, 68`), the last
unmeasured High/High risk — by (a) closing the verify→bank loop with `plumb verify --bank`
(N2, `docs/planning/discrepancy-corpus/prd.md:113-114`) and (b) running a small panel of
real runnable papers through the spine, banking each, and publishing the first honest
multi-paper coverage/precision/recall figure with denominators and label-authority markers.

## Affected areas (mapped)

### The `--bank` slice

- **No record-dir writer exists in `src/plumb`.** The live spine writes only the run area
  and (with `--out`) the signed bundle (`src/plumb/cli/live.py:154-157`); the only record
  writer is dev-time `tools/gate_run.py:118-124`. A `--bank` needs a record assembly
  function: `claims.json`, `bindings.json`, `trace.json`, `objects/` (locatable only),
  `paper.pdf|md`, `verdicts.json` (+ `environment.txt`/`source.json` if the record must
  also support `--out` replays, `replay.py:187-222`).
- **The claims-shape mismatch is the load-bearing gap.** The replay/bank chain reads only
  the curated six-field form `{text, metric, source, context, start, end}`
  (`replay.py:63, 152`); live `_spine` holds C1 `Claim` objects (`live.py:129`) with no
  `source`/`context`. Options: (a) synthesize the curated form from `Claim` + paper text;
  (b) write the C1 record form via `serialize_claims` and teach `read_record` to accept it
  through `parse_claims` + the admission gate — the bundle path already proves this read
  (`bundle/build.py:80`, `bundle/verify.py`). Open question for the PRD.
- **`objects/` hygiene.** The live capture store contains stderr (`diagnostic_only`,
  `capture.py:109-112`), which may carry local paths; `bank_case` copies every file in
  `objects/` (`store.py:205-217`). The writer must copy only `capture.locatable` (as
  `gate_run.py:122-123` does) or the no-local-path tests fail.
- **Everything else is in hand** after `verify_claims` (`live.py:153`): `bindings_bytes`,
  `trace`, `capture`, `paper_bytes`/`paper_format`, `descriptor.to_text()`,
  `checkout.source`. `SourceRecord` has no serializer — the six-field mapping must be
  written (`replay.py:65-67`).
- **Hook point:** after `verify_claims` in `_spine`; the natural design is write the record
  dir, then `bank_record` (`corpus.py:87-106`), which re-runs the replay chain — enforcing
  "a record that would not replay does not bank" for free; write-once/no-op semantics come
  from `bank_case` (`store.py:87-92`). `CorpusRefused → CORPUS_REFUSED` already wired
  (`cli/__init__.py:370`). `--from-record --bank` would bank a record already in hand.
  Nonclaims lane optional (live C1 rejections are a different population than the curated
  `unrepresentable.json`; lane is optional, `case.py:54`).

### The campaign

- **Selection rule fixed before running** — the `survey.md:6-14` criteria (openly licensed;
  public pure-Python/R code; laptop-CPU minutes; no run-time network; data bundled or
  generated; headline numbers printed/written as JSON/CSV; deterministic or seeded) plus
  PRD P2's anti-inflation guard (`gate-paper/prd.md:37-45`). The ReScience catalogue was
  already screened — all 13 candidates failed (figures-only, notebook-computed tables,
  unseeded stochastic aggregates, `survey.md:23-54`); the panel needs a wider (arXiv)
  search like AgroDesign's.
- **Per-paper template** (from `fixtures/gate/agrodesign/` + `tools/`): provenance README
  with SHA-256 pinning; a spec generator in the `agrodesign_spec.py` shape (rule-encoded
  data tables, spans found via exactly-once `unique_offset`); a `gate_run.py`-style dev-time
  run (real env build, freeze, `drift.json` M4a cross-check); committed record; offline
  tests (fixture grounding, byte-identical replay, C1 recovery floors, no-local-path scan,
  CLI `--from-record`); bank with owner-reviewed labels on every `DIVERGED`.
- **The report already pools** (`test_agrodesign_corpus_report.py:86-166` — per-case rows,
  totals with denominators and `authority`); the campaign's first slice of new code is the
  `--bank` fold-in, then the rest is fixture/dev-time work plus docs.
- **C1 recovery on new papers is unmeasured** — expect claim-recovery tuning per paper
  (`docs/technical/CAPABILITY_ROADMAP.md:85-87`); report per-paper recovery as conformance,
  never extraction coverage.
- **No other code-backed paper fixture exists** (`fixtures/gate/` = agrodesign only;
  `fixtures/papers/` = the 5 PDF-only blind-label fixtures). The campaign papers are the
  first multi-paper code fixtures.

## Ambiguities / open questions (for the PRD)

1. **Record claims form for live runs** — curated six-field form vs C1 record form for the
   live-written `claims.json`; must `read_record` accept both? (The bundle already reads the
   C1 form.)
2. **`--bank` semantics** — flag-only (default store `corpus/local/`) vs `--bank [--store
   DIR]`; interaction with `--from-record` (bank the record in hand?) and `--out` (both?);
   failure semantics when banking refuses (exit 1 with `CORPUS_REFUSED`, verdicts still
   rendered?).
3. **Record persist location for live runs** — temp dir per run, `WORK_ROOT` slot, or
   user-specified `--record DIR`? Only the banked case survives by default, or is the
   record kept?
4. **Nonclaims on the live path** — write C1 rejections to the record as `nonclaims.json`,
   or omit (lane optional)?
5. **Panel size & selection authority** — 3–5 papers; who selects (owner at dev time) and
   what happens to a paper whose repo won't run (UNVERIFIED cases bank with named causes —
   the honest number includes them, or the panel rule excludes them at selection time?).
6. **Per-paper scope** — does every paper get the full M4a drift cross-check, a signed
   bundle, and a C1-recovery floor test, or is that reserved for papers with `DIVERGED`s?

## Guardrail check (CLAUDE.md)

Execution-grounded only: verdicts come from `verify_claims`; labels are human and
owner-reviewed (`DIVERGED` → `review_required`); no egress — paper runs happen on the
user's compute at dev time (`tools/` precedent), never in tests/CI; `UNVERIFIED` is the
honest default and must be reported as such; a `DIVERGED` banks only with its evidence
chain and `review_required`. No constraint conflicts found.