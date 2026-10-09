# PRD — notebook-cell-locator (C4, follow-on)

Unit: C4's `notebook_cell` locator. Source: `docs/planning/_card/issue.md` (pbf handoff,
2026-10-10). Understanding: `understanding.md` in this directory. Owner: aliz.

## Problem statement

C3 now captures notebook cells as content-addressed `notebook_cell` artifacts
(`<relpath>#cell-<i>`, the canonical `outputs` JSON — `src/plumb/run/capture.py:136-187`),
but C4's bindings schema knows only `json_pointer` / `stdout_regex` / `csv_cell`
(`src/plumb/verify/bindings.py:80,97-101`), and the `_kind_mismatch` gate refuses anything
that does not end in `.json`/`.csv` (bindings.py:220-228). **A repo whose headline number is
computed in a notebook — the dominant failure mode across both selection passes
(`docs/planning/cross-paper-coverage/panel-run/screening.md:293-294`;
`docs/planning/gate-paper/survey.md:47-48`) — can be run and captured but every claim ends
`UNVERIFIED`.** Capture without the locator does not move R1's number
(`docs/planning/notebook-capture/understanding.md:18-19`); the locator is the named
immediately-next unit (`docs/planning/notebook-capture/prd.md:23`) and R1's named mitigation
(`docs/ROADMAP.md:90`).

## Goals & success metrics

- A claim can bind to a cell's canonical `outputs` array and decide a verdict on a synthetic
  notebook run: `REPRODUCED` when the bound cell output matches within the paper's written
  precision, `DIVERGED` (with `review_required`) when its own run contradicts it.
- No claim that R1 moved: this unit's metric is seam-proof + round-trip identity; moving the
  number on a real notebook paper is the successor unit (out of scope below) and is never
  credited to this one.
- **No new cause** enters any closed vocabulary — the binding-side quartet
  (`NO_BINDING`/`AMBIGUOUS_BINDING`/`BINDING_INVALID`/`UNPARSEABLE_VALUE`) plus
  `STALE_ARTIFACT` cover every outcome; `verify/causes.py` stays byte-identical and
  `tests/verify/test_cause_catalogue.py` keeps asserting emitted set == `CAUSES`.
- Every round-trip stays byte-identical with a `notebook_cell` binding: record →
  `--from-record` replay, `--bank`, `build_bundle`/`verify_bundle`.
- Full suite green (1936 today, strictly more), network-free under `tests/conftest.py`;
  real kernels run only at dev time.
- A dev-time probe records a stub-kernel notebook repo run through the live CLI to a
  cell-bound verdict (evidence doc, `notebook-capture` precedent).

## User scenarios

- **Notebook-computed table** (Perrin/JAMIA-demo class, `screening.md:293-294`): the paper's
  Table 1 is computed in `analysis.ipynb`, cell 3, as an `execute_result` with a printed
  number. The user writes the binding
  `{"claim_id": "...", "artifact": "analysis.ipynb#cell-3", "locator": {"kind": "notebook_cell", "pointer": "/1/data/text/plain/0"}}`
  and gets a verdict from the cell bytes in the object store — never a re-read of the working
  copy, never a committed value.

## Requirements

### Must-have

1. **Schema** (`bindings.py`): new kind `notebook_cell` with exactly the fields
   `{kind, pointer}`; pointer validated by the existing RFC 6901 rule (bindings.py:102).
   Grammar per **D1**.
2. **Kind-aim gate** (`_kind_mismatch`, bindings.py:220-228): a `notebook_cell` locator may
   name only an artifact matching `.ipynb#cell-<n>$`; a `json_pointer` locator still requires
   `.json` — the kinds stay disjoint; a mis-aim is `Binding.invalid` (per-entry
   `BINDING_INVALID`), never a file-level raise.
3. **Locate** (`locate.py`): dispatch branch for `NotebookCell`; read only through
   `Capture.read` (SHA-256 re-checked; a tampered store raises like today, locate.py:16-19);
   the located value carries the vertex evidence (artifact relpath, sha256, strict `Decimal`,
   `half_unit`; `float_repr` honored on the shared number-parse path, locate.py:99-112).
4. **Resolution semantics** over the canonical `outputs` array: pointer resolves to nothing →
   `NO_BINDING`; a list/object node leaf (e.g. `/…/text/plain` — stream `text` is a list of
   lines) is not a value → `UNPARSEABLE_VALUE` — **the pointer must address the element
   (`/…/text/plain/0`), Plumb never picks one**; `AMBIGUOUS_BINDING` is unreachable by
   construction — a JSON pointer resolves at most one node — and the PRD says so rather than
   inventing a many-case (see **D2**).
5. **Staleness** (**D3**): `_stale_target` resolves the bound cell to its notebook file
   (`analysis.ipynb#cell-0` → `analysis.ipynb`) and refuses `STALE_ARTIFACT` with bytes never
   read — C3 records staleness per file (capture.py:126-130), never per cell. This closes the
   exact leaked-stale shape of `test_false_diverged_guard.py:70-84`, extended and
   mutation-checked for the cell path (**R2**) — a stale notebook being read through a cell
   name is the unit's false-`DIVERGED` risk.
6. **Serialization & render**: canonical `verdicts.json` locator JSON for the new kind
   (`serialize.py:72-83`, pinned by verdict-serialize tests); the table's locator column
   renders the cell name and pointer rather than `""` (`cli/render.py:120-133`).
7. **Round-trips**: record → replay byte-identical, `--bank` fold-in, and bundle
   build/verify with a `notebook_cell` binding. `bindings.json` is verbatim bytes at every hop
   (record.py:73, replay.py:134, build.py:81, store.py:194) — expected to need **no** member
   or manifest change; the tests prove it (record_writer/replay/bank_flag/notebook_spine
   patterns).
8. **False-`DIVERGED` guard**: notebook-cell scenarios join the guard's `SCENARIOS`
   (test_false_diverged_guard.py:88-106) and the mutation set (160-180); no harness-side
   failure can become `DIVERGED`.

### Should-have

9. **Dev-time probe**: `tools/notebook_locator_probe.py` runs a synthetic notebook repo
   through the live CLI with a stub `jupyter`; a cell-bound claim decides; evidence recorded
   as `docs/planning/notebook-cell-locator/probe_20261010.md` (bytes, not paths; no kernel, no
   network).
10. **Catalogue row**: a `notebook_cell`-produced `NO_BINDING`/`UNPARSEABLE_VALUE` row joins
    `test_cause_catalogue.CASES` (no vocabulary change — optional, see **D5**).

### Nice-to-have

- None beyond the above; scope is deliberately tight (the real notebook paper fixture is the
  follow-on, out of scope below).

## Technical considerations

- **The seam is four schema-typed spots**: `bindings.py` (union, `_LOCATOR_FIELDS`, `_locator`,
  `_kind_mismatch`), `locate.py` (dispatch + `_notebook_cell` reader mirroring `_json`),
  `serialize.py` `_locator`, `cli/render.py` `_locator_text` — everywhere else (`record`,
  `replay`, `bundle`, `corpus`) carries bindings as raw bytes (`understanding.md`, "Round-trip
  layers").
- **Canonical bytes**: `json.dumps(cell["outputs"], sort_keys=True, ensure_ascii=False,
  separators=(",",":"), allow_nan=False) + "\n"` (capture.py:174-183); array order is stable;
  `execution_count` is excluded and never addressable.
- **v5 indent**: the pointer indexes the array natively (`/1/…` = output slot 1); no separate
  output field to validate.
- Dependencies: C3 notebook capture (shipped 2026-10-08, `0d60c59`) and the C4 first slice
  (shipped 2026-09-25). Nothing blocks; nothing else changes.

## PRD decisions

- **D1 — Grammar: pointer into the outputs array.** A `notebook_cell` locator is
  `{"kind": "notebook_cell", "pointer": "/1/data/text/plain/0"}` — one mechanism, exactly
  mirroring `json_pointer` semantics. Confirmed with the owner.
- **D2 — "Many" is unreachable; say so.** A JSON pointer resolves at most one node, and the
  canonical array's per-object keys cannot repeat (duplicate keys collapse at notebook-read
  time). The never-a-guess contract is enforced by `NO_BINDING` (nothing resolves) and
  `UNPARSEABLE_VALUE` (a list/object node is not a value — stream `text` is a line list, so
  the binding points at the element, `/…/text/0`, never at the list);
  `AMBIGUOUS_BINDING` stays defined in the vocabulary and documented as unreachable on this
  path — not silently dropped, deliberately un-aimable.
- **D3 — Staleness is resolved cell → file before the guard reads anything.** The bound
  artifact's `#cell-<n>` suffix is stripped to its notebook relpath and the stale check runs
  on the file record; a stale notebook makes its cells `STALE_ARTIFACT` with bytes never
  read (constraint #5, reproduce what ran).
- **D4 — `float_repr` applies to located notebook numbers** on the shared parse path; a
  notebook that wrote `2.5` (not `2.500`) is the program's exact double, not a rounding —
  same rule as pandas/json, same audit trail (bindings.py:29-36).
- **D7 — Leaf transport stays float-free.** The located value is always *text*: a JSON string
  leaf uses its text verbatim; a JSON number leaf is transported as its JSON text via
  `json.dumps(leaf, allow_nan=False)` (shortest round-trip — the bytes the artifact wrote),
  then `strict_decimal` — the only numeric parse, and no `float` object ever reaches a
  comparison (the float-free invariant is pinned by test). Whether that text is a rounding or
  the program's exact double is the binding's `float_repr` declaration, exactly as for any
  captured `.json` artifact.
- **D5 — No new causes, no vocabulary changes.** Mis-aim (grammar, wrong artifact kind) →
  `BINDING_INVALID`; absent cell artifact or unresolving pointer → `NO_BINDING`; non-scalar
  or non-numeric leaf → `UNPARSEABLE_VALUE`; stale file → `STALE_ARTIFACT`. The four pinned
  vocabulary sites stay byte-identical; the catalogue may grow a row, never a name.
- **D6 — Serialization/rendering:** canonical locator JSON `{"kind": "notebook_cell",
  "pointer": "/1/data/text/plain/0"}` in `verdicts.json` (byte-identical); the table renders
  `<cell part> /<pointer>`. Exact cell-name rendering pinned by render tests.

## Risks & open questions

- **R2 — false `DIVERGED` through a stale cell** (the unit's core risk): mitigated by D3 plus
  a mutation-checked guard extension; every `DIVERGED` carries `review_required`
  (verdict.py:107-109). The leaked-stale scenario (test_false_diverged_guard.py:70-84) is the
  template.
- **R1 — the number still needs a real paper**: this unit proves the seam offline; moving
  R1's number on a real notebook paper is the named follow-on (a Perrin-style fixture,
  dev-time) — out of scope, tracked in the understanding's guardrail check.
- **Open:** whether nbconvert's `text` output is always a string-list under `data/text/plain`
  (the notebook-capture probe recorded `text` list bytes — `spine/probe_20261008.md`); the
  pointer grammar handles both, the leaf rule decides.
- **Open:** `test_cause_catalogue` row (should-have #10) — harmless, non-blocking.

## Out of scope

- Real notebook paper fixture + R1 panel addition (follow-on dev-time unit, Perrin-style).
- The C2 poetry env policy and C4 figure-with-data locators (the other named engine gaps,
  `screening.md:296-298`).
- New causes in any vocabulary; `AMBIGUOUS_BINDING` gets no new emitter.
- Binding proposer (`PROPOSER_UNGROUNDED` stays reserved); `execution_count` addressing;
  whole-file `notebook` artifacts as bind targets (cells are the unit of verdict); notebooks
  whose cells carry no outputs (no artifact → `NO_BINDING` at most).

## Guardrail check (CLAUDE.md)

Execution decides: the locator only locates; `decide` compares in pinned `Decimal`; run
causes govern first; a `DIVERGED` requires the artifact's own run and carries
`review_required`. No egress; tests offline with synthetic notebooks on a stub runner
(`tests/run/test_capture.py:78-86` pattern); real kernels only at dev time; test-first — the
acceptance tests are written before the code (issue.md items 1-5).