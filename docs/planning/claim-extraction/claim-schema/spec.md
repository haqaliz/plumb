# Aspect 1 — `claim-schema`

Parent: [`../prd.md`](../prd.md) · Covers **M1, M2, M7, M8, M10, M14** · Depends on:
nothing · Gates: aspects 2 and 3.

## Problem slice

Every later aspect constructs or serializes a `Claim`. Until the record exists and its
value semantics are pinned, nothing else can be written test-first. This aspect also
bootstraps the Python package, because there is no `pyproject.toml`, no `src/`, and no
test runner today.

**Outcome:** a typed, importable `Claim` (plus `StudyParameter`) whose value semantics
cannot silently lose precision, and a green test suite that runs offline.

## In scope

1. **Package bootstrap (M10, M14).** `pyproject.toml` via `uv` with a committed
   lockfile; `src/plumb/extract/` (`ARCHITECTURE.md:53`); pytest; a socket-blocking
   fixture that fails any test attempting network. Runtime deps stdlib / pure-parsing
   only — no packages that download models at import.
2. **`Claim` record (M1).** Fields: `reported_value`, `units`, `metric`/`subject`,
   `location`, `artifact_hint`, `tolerance_hint` (nullable), content-derived `id`.
3. **Value semantics (M2).** `reported_value` carries **verbatim text + `Decimal`** —
   never float.
4. **`location` as a tagged union (M7).** Char offsets over normalized text; round-trips
   to the exact source span. Shaped so PDF's page+bbox can be added without a migration.
5. **`StudyParameter` record (M11, shape only).** Minimal; populated in aspect 2.
6. **No `confidence` field (M8).**

## Out of scope

Selection logic, the admission gate, table parsing, dedup, serialization format, the
paper hash (aspects 2–3). PDF, DOI, the BYOK proposer, tolerance policy, locator
grammar (out of the whole slice).

## Acceptance criteria (failing tests first)

- A `Claim` cannot be constructed without `reported_value`, `units`, `metric`,
  `location`, `artifact_hint`. `tolerance_hint` accepts `None`.
- `reported_value` round-trips verbatim for: `p < 0.001`, `0.85 ± 0.03`,
  `95% CI [0.81, 0.89]`, `~10,000`, `12–15%`.
- `0.870` and `0.87` are **not equal** as `reported_value`s — significant figures
  survive.
- No float appears anywhere in the value path (assert on types).
- `location` round-trips: slicing the normalized text by the stored offsets returns the
  exact source span.
- `Claim` has no attribute named `confidence` (explicit negative test — it is a
  guardrail, not an omission).
- The suite fails loudly if any test opens a socket.
- `uv sync --frozen` succeeds offline from the committed lockfile.

## Risks

- **R2** (`ROADMAP.md:57`): a float leaking into the value path is the upstream seed of
  a false `DIVERGED`. The type assertions above are load-bearing, not stylistic.
- Guardrail `CLAUDE.md` #1: the `confidence` negative test exists so a later change
  can't quietly add a field that becomes `if confidence > 0.9` at verdict time.

## Open questions

- Test directory layout and module filenames: docs are silent — decide in `tech-plan`.
- `StudyParameter`'s full shape is provisional until C7 is built.
