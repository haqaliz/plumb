# C5 benchmark — precision and recall over the public corpus

Every figure below is regenerated from the three committed gate records, not typed by
hand. Rebuild with `uv run python tools/benchmark.py`; CI runs
`uv run python tools/benchmark.py --check`, which fails if this file is stale.

**Label authority: `owner`.** Precision counts confirmed `DIVERGED`s over the
`DIVERGED`s a human reviewed; recall counts confirmed `DIVERGED`s over every labeled
claim. Labels were written by the owner (see `docs/ETHICS.md` §3); third-party labels
do not exist yet.

## Panel

- AgroDesign — arXiv:2603.09041 (Python/R data analysis; script entry point)
- Perrin — arXiv:2401.11842 (R; recorded environment drift, not run-to-run stable at the paper's written precision)
- Burtsev — arXiv:2609.00137 (Jupyter notebook; the `notebook_cell` locator)

Each row of the report is a content-addressed case id:

- `941b556bea2792b1c24abd99ca0348c33d57861b5e18b074dbbb529583141de9` — AgroDesign
- `3f7f808d2861cff8fe838a5f2c65bebd6aac53f7d7630ba373fafd0b9ef70b95` — Perrin
- `db99db77e4e15da01fdd2b7e5e7a880f7f005aaa89a518187bbc6be4d264c722` — Burtsev

## Report

```
CASE                     | CLAIMS | BOUND | REPRODUCED | WITHIN-TOLERANCE | DIVERGED | UNVERIFIED | LABELED | CONFIRMED
-----------------------------------------------------------------------------------------------------------------------
3f7f808d2861cff8fe838a5… | 16     | 16    | 2          | 0                | 14       | 0          | 14      | 0        
941b556bea2792b1c24abd9… | 86     | 86    | 85         | 0                | 1        | 0          | 1       | 1        
db99db77e4e15da01fdd2b7… | 31     | 30    | 30         | 0                | 0        | 1          | 0       | 0        
total (3 cases)          | 133    | 132   | 117        | 0                | 15       | 1          | 15      | 1        

  coverage: 132/133 bound
  precision: 1/15 (owner)
  recall: 1/15 (owner)
```

## Refuted-verdict accounting

The panel produced **15 `DIVERGED`** verdicts: **1 confirmed**, **14 refuted** on owner review. A refuted divergence is a reproducibility finding about the artifact, not a paper error: Perrin's survival draws are unseeded, and three full runs moved every claim by more than the paper's written precision.

Coverage: **132/133 bound** across 3 cases.
Precision: **1/15 (owner)**. Recall: **1/15 (owner)**.

## What this number is not

It is not a survey: three papers selected by a fixed pre-written rule, one of which is
not run-to-run stable. It is not a claim about the authors. It is the honest precision
of the engine on the panel it has, and it is meant to move only when the corpus grows.
