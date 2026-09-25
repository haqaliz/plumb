# Aspect `locators` — bindings file and deterministic locators

Parent: [`../prd.md`](../prd.md) (M1, M2; D4 `scale` and D2 `tolerance` are parsed here but
applied in `compare`).

## Problem slice & outcome

Given a user-written bindings file and a C3 `Capture`, produce for each binding either a
**located value** — the verbatim text, its strict `Decimal`, its written precision, and the
artifact (relpath + sha256) it came from — or a **named cause**. No comparison happens here.

## In scope

- `load_bindings(raw: bytes, claim_ids)` → `Bindings`: schema validation; whole-file
  `BindingInvalid` for malformed JSON, missing/unknown fields, a duplicate `claim_id`, a
  `claim_id` not in `claim_ids`, a duplicate id inside `claim_ids`, `<stderr>` as artifact,
  a `tolerance`/`scale` that isn't a non-negative strict-decimal *string* (a JSON number is
  refused — it would have passed through `float`).
- Per-entry locator validity → `BINDING_INVALID` (not raised): bad RFC 6901 syntax, an
  uncompilable regex, a regex with ≠ 1 capture group, a `csv_cell` without exactly one row key.
- `locate(binding, capture)` → `Located | cause`, reading bytes **only** via
  `Capture.read`:
  - target relpath is a `StaleOutput` → `STALE_ARTIFACT`, and `Capture.read` is never called;
  - target not among `capture.locatable` → `NO_BINDING`;
  - `json_pointer`: decode UTF-8, `json.loads(parse_float=Decimal, parse_int=Decimal,
    parse_constant=<refuse>, object_pairs_hook=<refuse duplicates>)`; resolve; missing →
    `NO_BINDING`; duplicate key on the path → `AMBIGUOUS_BINDING`; non-scalar / bool / null /
    string that isn't a strict decimal / NaN / Infinity → `UNPARSEABLE_VALUE`;
  - `stdout_regex`: 0 matches → `NO_BINDING`, > 1 → `AMBIGUOUS_BINDING`;
  - `csv_cell`: `utf-8-sig`, header row, column absent → `NO_BINDING`, duplicated in header
    → `AMBIGUOUS_BINDING`; row key matching 0 / > 1 rows → `NO_BINDING` / `AMBIGUOUS_BINDING`;
  - undecodable bytes or a cell that isn't a strict decimal → `UNPARSEABLE_VALUE`.
- Strict decimal = optional sign, digits, optional fraction, optional exponent, surrounding
  whitespace stripped; no thousands separators, no `%`, no `inf`/`nan`.
- Written precision of a located value: the half-unit `5 × 10^(exponent − 1)` of the
  `Decimal` built from the located *text* (JSON number literals keep their text via
  `parse_float=Decimal`).

## Out of scope

Comparison, tolerance semantics, verdicts, serialization, notebook locators, any proposer.

## Acceptance criteria (failing tests first)

1. A valid bindings file with one entry per locator kind loads; each malformed case above
   raises `BindingInvalid` naming the offending entry.
2. A JSON number tolerance (`{"abs": 0.01}`) raises `BindingInvalid`; `{"abs": "0.01"}` loads.
3. Each locator resolves its happy path from a real `Capture` (built by C3's `capture_outputs`
   over a tmp run area) to the exact verbatim text and `Decimal`, with the artifact sha256.
4. Each cause above has its own test (`NO_BINDING`, `AMBIGUOUS_BINDING`, `UNPARSEABLE_VALUE`,
   `BINDING_INVALID`, `STALE_ARTIFACT`).
5. `STALE_ARTIFACT`: a spy on `Capture.read` proves it is never called for a stale target.
6. A JSON value `0.1` locates as `Decimal("0.1")` exactly, and no `float` appears anywhere
   (spy: `json.loads` called with `parse_float=Decimal`; value type asserted).
7. Written precision: `0.87` → `0.005`, `0.870` → `0.0005`, `12` → `0.5`, `1.5e3` → `50`.
8. A tampered object-store entry surfaces `Capture.read`'s `ValueError` — it is not
   swallowed into a cause (an integrity failure is not a binding failure).

## Dependencies & sequencing

Consumes `plumb.run.capture` only. Independent of `compare`; both feed `verdict-seam`.

## Risks

- Criterion 8 is a judgement call: a tampered store is a harness integrity failure. Raising
  (not recording) keeps it out of every verdict; `verdict-seam` must not catch it.
