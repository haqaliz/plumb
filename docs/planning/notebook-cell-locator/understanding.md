# Understanding — notebook-cell-locator (C4 follow-on)

Date: 2026-10-10. Source: `docs/planning/_card/issue.md` (pbf handoff from plumb-next,
2026-10-10; no GitHub issue — the id lives in the branch and PR). Dig agents mapped
`src/plumb/verify/` and the `run`/record/replay/bundle/corpus ripple points.

## What the work is really asking

C4's `notebook_cell` locator: let a claim bind to a captured cell artifact
(`<relpath>#cell-<i>`, the canonical `outputs` JSON) and decide a verdict. This is the
named immediately-next unit after notebook capture shipped (`docs/planning/notebook-capture/prd.md:23`);
capture alone yields no verdicts and R1's number does not move
(`docs/planning/notebook-capture/understanding.md:18-19`). Verdicts are the point — this is
C4, the moat.

## The seam (mapped)

- **`verify/bindings.py`** — `Locator = JsonPointer | StdoutRegex | CsvCell` (bindings.py:80);
  `_LOCATOR_FIELDS` (97-101) is the schema table; `_locator` (185-217) raises `BindingInvalid`
  for unknown kinds/field sets; `_kind_mismatch` (220-228) gates artifact names per kind
  (JsonPointer needs `.json` suffix, StdoutRegex needs `<stdout>`, CsvCell needs `.csv`).
  **`analysis.ipynb#cell-0` fails the `.json` suffix gate today** — the block is purely the
  name gate; the artifact *is* otherwise locatable (`capture.py:93-96`, cell artifacts are
  `diagnostic_only=False`).
- **`verify/locate.py`** — dispatch is an `isinstance` chain (90-96); order is the guarantee:
  `binding.invalid` → `BINDING_INVALID` (81-82), `_stale_target` → `STALE_ARTIFACT`, bytes
  never read (83-84, 102-103), absent target → `NO_BINDING` (85-87), then
  `capture.read(artifact)` (89, hash re-checked, ValueError propagates — never caught,
  locate.py:16-19). Zero/many → `NO_BINDING`/`AMBIGUOUS_BINDING` (e.g. duplicate keys in
  `_json`, 136-140,153-154). Number parsing: `strict_decimal` → `UNPARSEABLE_VALUE`,
  `half_unit` or `Decimal(0)` under `float_repr` (99,106-112).
- **`verify/__init__.py`** — `verify_claims` (129-153) is locator-agnostic; run causes govern
  first (141-162); per claim: no binding → `NO_BINDING`, `Unlocated` → its cause, else
  `decide` (165-194). `Verdict.__post_init__` refuses decided verdicts without evidence;
  `review_required` iff `DIVERGED` (verdict.py:107-109). No seam change needed to add a kind.
- **Canonical cell bytes** — `capture.py:157-187`: `json.dumps(cell["outputs"], sort_keys=True,
  ensure_ascii=False, separators=(",",":"), allow_nan=False) + "\n"`; output array order never
  reordered; `execution_count` excluded. Artifact `kind="notebook_cell"`,
  relpath `<nb>#cell-<i>` (0-based `cells` index, capture.py:140,168), `mtime_ns` = the
  notebook file's mtime (143).
- **Round-trip layers** — `bindings.json` is verbatim bytes through record
  (`cli/record.py:73`), replay (`cli/replay.py:134`), bundle (`bundle/build.py:81`), corpus
  bank (`corpus/store.py:194`, never re-serialized) — a new kind survives as bytes. But every
  verdict seam re-parses via `load_bindings` (record.py:76, replay.py:97, bundle/verify.py:201,
  cli/corpus.py:123) — parseability is the real contract. Bundle object acceptance is by sha
  against locatable artifacts, no kind whitelist (`bundle/verify.py:215-225,256-259`) —
  `notebook_cell` objects already pass. Manifest/trace/case schemas are locator-agnostic.
  Golden files (`tests/cli/golden/table_agrodesign.txt`, the AgroDesign record, `bundles/`)
  need **no regeneration** — they bind `.json`/`<stdout>`/`.csv` only.
- **Schema-typed spots that need code** — `bindings.py` (union, fields, `_locator`,
  `_kind_mismatch`), `locate.py` (dispatch + a `_notebook_cell` reader mirroring `_json`),
  `verify/serialize.py:72-83` (`_locator` raises on unknown types — `verdicts.json` is
  byte-typed), `cli/render.py:120-133` (`_locator_text`, else renders `""`).

## Key findings / decisions the PRD must make

1. **Grammar.** The artifact already carries the cell index (`analysis.ipynb#cell-0`), so the
   locator needs: which output slot of the `outputs` array (index, or discriminator —
   `output_type`/`stream.name`?), and a sub-pointer into that output's JSON. Mirror `_json`'s
   mechanics (RFC 6901 pointer + duplicate-key `AMBIGUOUS_BINDING` + missing → `NO_BINDING`).
   `execution_count` is already excluded from the canonical bytes — never addressable.
2. **Staleness is per file, not per cell.** C3 records staleness on the notebook file's
   relpath (`analysis.ipynb`), never on `#cell-<i>` records
   (`post_stale` at capture.py:126-130; cell artifacts carry the file's `mtime_ns`, 143).
   `_stale_target` (locate.py:102-103) keys on the bound artifact's relpath — a stale leak
   through a cell name is the exact shape the guard's leaked-stale scenario pins
   (`test_false_diverged_guard.py:70-84`). The locator must strip `#cell-<i>` and check the
   notebook file's stale record — this is acceptance item 2 and a false-`DIVERGED`-guard
   concern (R2).
3. **No new causes.** `NO_BINDING` / `AMBIGUOUS_BINDING` / `BINDING_INVALID` /
   `UNPARSEABLE_VALUE` / `STALE_ARTIFACT` cover every mis-aim; the PRD must say so — all four
   vocabularies stay closed (`verify/causes.py:79-97`; pinned by `test_cause_catalogue.py:62-63`).
4. **`_kind_mismatch` rule.** `notebook_cell` kind requires an artifact ending in `#cell-<n>`
   (and not `<stdout>`/stderr); `.json` pointer locators remain unable to read cell artifacts
   (or should the `.json` rule be relaxed instead? — PRD decision; integrity says keep kinds
   disjoint).
5. **`float_repr`** applies at number-parse time (locate.py:106-112), so the notebook path
   gets it for free (e.g. `2.5` in a notebook JSON output).

## Contradictions / hazards surfaced

- **The stale-leak gap is real and must be closed by the new locator, not assumed away** —
  the leaked-stale scenario (test_false_diverged_guard.py:70-84) fabricates an artifact that
  is both stale-listed and present; with cell names, the stale listing is the notebook file,
  so `_stale_target` must resolve cell → file before checking. This is the unit's R2 core;
  the pick's caveat (issue.md:26-27) called it.
- README.md's "not built" row is stale (lists value-kinds/corpus as not built) — not this
  unit's scope, do not propagate.
- No real notebook paper fixture exists; dev-time work (Perrin-style) belongs after the
  locator lands, so R1's number moves on a real paper — out of scope for this unit but the
  named follow-on (issue.md:28-30).

## Guardrail check (CLAUDE.md)

Execution decides: the locator only locates; `decide` compares; run causes govern first;
`DIVERGED` requires the artifact's own run and carries `review_required`. No egress. Tests
offline with stub-runner/synthetic notebooks (`tests/run/test_capture.py:78-86` pattern).
Test-first: red before green per acceptance (issue.md:31-43).

## Open questions for the PRD

1. Locator field shape: `{"kind": "notebook_cell", "output": <index|int>, "pointer": <RFC6901>}`
   vs a discriminator field; is `output` optional (default: first matching output — or is an
   implicit default a guess? AMBIGUOUS_BINDING says no).
2. Staleness resolution: strip `#cell-<i>` from the bound artifact to check the notebook
   file's stale record — confirm `_stale_target` mechanics can take the resolved relpath.
3. Should a `json_pointer` be allowed to target `#cell-` artifacts directly, or is the new
   kind the only door (kinds stay disjoint)?
4. Serialization/render: exact canonical JSON for the new locator in `verdicts.json` and the
   table's locator column.
5. Catalog test: add a `notebook_cell` row to `test_cause_catalogue.CASES` (allowed — no
   vocabulary change) or leave the catalogue as-is.