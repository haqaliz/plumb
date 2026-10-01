# Brief — discrepancy-corpus (C5, first slice)

Source: `pbf feat discrepancy-corpus` handoff from `plumb-next` (2026-10-01). No GitHub
issue exists for this work; the id lives in the branch and PR.

## Brief

Build C5's first slice, test-first: the discrepancy-corpus store under `src/plumb/corpus/`
per `docs/technical/ARCHITECTURE.md:148-154` — every `(claim, re-derived value, verdict,
locator, cause)` from a verify run banks as a self-contained, replayable, human-labelable
case under gitignored `corpus/local/`, with canonical serialization, and a `--json`-stable
bank command or seam to fold the existing AgroDesign record in as case #1 without re-running
it. The benchmark scaffold measures precision/recall/coverage against human labels, excludes
`UNVERIFIED` from precision, and never lets the engine label its own cases — with the
coverage number honestly reported as the R1 measurement (first real numbers may be ugly;
`UNVERIFIED` is the honest default). Acceptance tests, written first: banking a committed
AgroDesign record round-trips byte-identically; a case re-derives its verdict from its own
stored trace; labeled-precision math excludes `UNVERIFIED`; and the store never mutates an
existing case.

## Design anchor

- `docs/technical/ARCHITECTURE.md:148-154` — C5: discrepancy corpus (`src/plumb/corpus/`),
  cases under gitignored `corpus/local/`, precision/recall/coverage measured against human
  labels, `UNVERIFIED` excluded from precision, engine never labels its own cases.
- `docs/technical/CAPABILITY_ROADMAP.md:209-217` — C5: accumulate every (claim, re-derived
  value, verdict, locator, cause); publish a precision/recall benchmark over a public paper
  corpus. "Precision on `DIVERGED` is the number the whole reputation rests on."
- `docs/ROADMAP.md:68` (R1), `:32-33` — cross-paper coverage is unmeasured; C5 is the
  instrument that measures it.