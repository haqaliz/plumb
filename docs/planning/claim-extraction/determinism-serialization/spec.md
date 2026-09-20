# Aspect 3 — `determinism-serialization`

Parent: [`../prd.md`](../prd.md) · Covers **M6, M9, M13** · Depends on: aspect 1
(`claim-schema`) · Independent of aspect 2 — can be built in parallel once the record
exists.

## Problem slice

"Byte-identical output" has no referent without a defined serialized form, and C6 has
nothing to bundle. This aspect makes C1's output a **contract** rather than just code,
and pins the determinism controls that a Python text pipeline breaks by default.

**Outcome:** the same paper in, the same bytes out — across runs, across processes,
across machines.

## In scope

1. **Serialized form (M6).** JSON with `sort_keys`, `ensure_ascii`, `separators`,
   indent, and trailing newline all pinned explicitly.
2. **Paper hash (M6).** Content hash of the **normalized** text — the same bytes the
   `location` offsets index — with the algorithm named explicitly. `hashlib` only.
3. **Determinism controls (M9).** `.gitattributes` with `eol=lf`; no `set` iteration and
   no `hash()` (`PYTHONHASHSEED` varies per process) — sort by an explicit total key;
   no timestamps; no absolute paths; Unicode normalized exactly once; a documented
   overlap-resolution rule for regex alternation (`re` is leftmost-first, so reordering
   alternations silently changes winners); single-threaded as a stated contract.
4. **Dedup by value-identity (M13).** Merge locations into one claim only when the
   verbatim value string is byte-identical; near-duplicates stay separate.

## Out of scope

Bundle signing (C6), the corpus format (C5), selection logic (aspect 2), the record's
field set (aspect 1).

## Acceptance criteria (failing tests first)

- Serializing the same input twice in one process yields byte-identical output.
- Serializing in **two separate processes** yields byte-identical output (catches
  `PYTHONHASHSEED`; run the test under at least two different seed values).
- Output contains no timestamp and no absolute path (assert on the serialized bytes —
  note `Path.resolve()` differs under symlinks, e.g. `/tmp` → `/private/tmp`).
- A CRLF fixture and its LF twin produce identical `location` offsets after
  normalization.
- The paper hash covers the normalized text: changing only line endings does **not**
  change the hash; changing a character does.
- Two claims with byte-identical `reported_value` in different locations merge into one
  claim with two locations.
- `0.87` and `0.870` in the same paper remain **two** claims (the M2/M13 boundary).
- The content-derived `id` is stable across processes and unchanged by a location merge.

## Risks

- Determinism failures are intermittent by nature — a single-process test passes while
  the contract is broken. The two-process test is the load-bearing one.
- **R2** (`ROADMAP.md:57`): if dedup ever canonicalizes numerically, it reintroduces the
  lossy normalization M2 exists to prevent. Value-identity only, enforced by the
  `0.87` / `0.870` test above.

## Open questions

- 🔴 **Are `.87` and `0.87` one claim or two?** Aspect 1 made value-identity the
  verbatim `text` string, so `0.87`, `.87` and `0.870` are currently **three**
  identities. That errs toward splitting rather than merging, which is the conservative
  direction — a false split is visible in the coverage number, a false merge silently
  loses a claim. But a paper writing `.87` in a table and `0.87` in the abstract would
  double-count one result in the Phase 0 denominator. **This aspect owns the decision.**
  Note the constraint: any canonical form used for identity reintroduces exactly the
  normalization M2 exists to prevent, so if the answer is "one claim", the canonical
  form must be used for *identity only* and never for comparison.
- Which hash algorithm to name (sha256 is the obvious default; it must be *recorded*,
  not just chosen, since C6 replay depends on it).
- Whether to embed a schema/tool version in the output: doing so changes the
  determinism contract from "input → bytes" to "input + version → bytes". Decide in
  `tech-plan`.
