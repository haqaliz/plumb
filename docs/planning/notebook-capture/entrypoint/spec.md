# entrypoint — aspect spec (`notebook-capture`)

Problem slice: PRD M1–M2. `ManifestScan` learns which root `*.ipynb` a checkout has, and
`resolve_entrypoint` gains a third, **fallback** discovery rule: when neither a
`[project.scripts]` entry nor a root `main.py` exists, exactly one root notebook resolves to
`EntryPoint(argv=("jupyter","nbconvert","--to","notebook","--execute","--inplace","<relpath>"),
source="notebook")`; several → `ENTRYPOINT_AMBIGUOUS`; none → `ENTRYPOINT_MISSING`. No
execution, no capture, no new causes.

## In scope

- `ManifestScan.notebooks: tuple[Path, ...]` — root-level `*.ipynb`, sorted, filled by
  `scan_manifests`; nested paths (including `.ipynb_checkpoints/`) are not candidates
  (root-only doctrine, `src/plumb/intake/manifest.py:5-7`).
- `resolve_entrypoint` fallback: notebooks are considered **only when the existing rules
  yield zero candidates** — a scripts entry or a root `main.py` shadows notebooks entirely,
  and kinds are never mixed into one ambiguous pool.
- The exact notebook argv and `source="notebook"`; module docstring rule list updated
  (`src/plumb/run/entrypoint.py:1-17`).
- The `EntryPointMissing` message updated to name the notebook rule.

## Out of scope

- Execution, capture, trace changes (aspect `capture` / `spine`).
- Nested notebook discovery, an explicit-entry CLI flag, papermill/R, any new cause.
- `.ipynb` files that are not at the checkout root.

## Acceptance criteria (testable, written failing first — all offline)

1. A checkout with only a root `analysis.ipynb` resolves to argv
   `("jupyter","nbconvert","--to","notebook","--execute","--inplace","analysis.ipynb")` and
   `source == "notebook"`.
2. Two root notebooks → `EntryPointAmbiguous` (message carries both candidate argvs);
   only a nested/`.ipynb_checkpoints` notebook → `EntryPointMissing`.
3. A root notebook plus a root `main.py` → `main.py` wins (`source == "main.py"`), no
   ambiguity; plus a single `[project.scripts]` entry → the script wins
   (`source == "pyproject-script"`).
4. `scan_manifests` records root notebooks sorted; absence is `()`; a root notebook does not
   disturb any existing manifest field.
5. Full suite green; no network; the run-package cause vocabulary untouched.

## Dependencies and sequencing

None (first aspect). `capture` and `spine` consume the `source="notebook"` argv shape.

## Open questions / risks

- A failing root `main.py` shadows a working notebook (no CLI `--entrypoint` flag) — accepted
  in the PRD, deferred to the CLI-knobs slice.
- Root-only discovery will miss `notebooks/analysis.ipynb` — named follow-on N1.
