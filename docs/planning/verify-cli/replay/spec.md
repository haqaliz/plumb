# replay — aspect spec

Problem slice: `--from-record <dir>` — the offline, CI-testable path that replays a committed
gate record (`fixtures/gate/agrodesign/`) through `verify_claims` and produces the same verdicts
the record committed. This is the acceptance surface the byte-identical guarantee is pinned on.

## In-scope requirements

- `plumb verify --from-record <dir>` reads the record's own `claims.json`, `bindings.json`,
  `trace.json` and `objects/` directory; `<paper>`/`<repo>`/`--rev`/`--bindings`/`--no-env-build`
  are not accepted with `--from-record` (usage error, exit 2).
- Re-derivation: `parse_claims` (records, never a second door to `Claim` — the admission gate
  re-admits via `readmit`, `src/plumb/extract/admit.py:441-475`), `parse_trace` (refuses a
  mismatched id, `src/plumb/run/trace.py:134-180`), `Capture` built from the record's
  `objects/` store + trace artifacts (pattern: `tests/gate/test_agrodesign_replay.py:34-47`),
  `load_bindings` against the record's claim ids, `verify_claims(claims, bindings,
  Completed(trace, capture))`.
- Cross-check: if the record contains `verdicts.json`, the re-derivation must match it
  byte-for-byte (`serialize_verdicts` equality); a mismatch is a named failure
  (`RECORD_INVALID`, detail naming the record) — the honesty check the PRD requires.
- Output: the shared renderer (table or `--json`) on the re-derived `VerdictSet`; exit code
  per the PRD contract (0 iff every claim decided).
- `--out DIR` works in replay mode: rebuilds the signed bundle from the record's members
  (claims re-admitted through the gate, paper read from the record dir when present and
  `--no-paper` not given, bindings bytes, trace, capture store, environment.txt, source from
  trace/record) via `build_bundle`; the rebuilt bundle must pass `verify_bundle`.
- Missing members (`claims.json`, `bindings.json`, `trace.json`, `objects/`) →
  `RECORD_INVALID` with the missing member named.

## Out-of-scope boundaries

- No live resolution/run in this aspect (that's live-spine).
- No paper extraction in replay mode — the record's claims are the source of truth; the
  paper is only read (from the record dir or `--out`'s needs) for bundling, never re-extracted.
- No writing back into the record dir; `--out` writes elsewhere.

## Acceptance criteria (testable, written failing first)

1. `plumb verify --from-record fixtures/gate/agrodesign/ --json` exits 0 and its stdout
   matches the committed record: 86 claims, 85 REPRODUCED / 1 DIVERGED, coverage numbers equal
   to the committed `verdicts.json`'s derived coverage, and every per-claim verdict equal to
   the committed one (byte-identical against the golden).
2. `--from-record` with `--bindings`, `<paper>` or `<repo>` arguments exits 2 (usage).
3. A record whose `trace.json` id mismatches its `objects/` (tampered copy) exits 1 with
   `RECORD_INVALID` — never a traceback, never a wrong verdict.
4. A record missing `objects/` (or any member) exits 1 with `RECORD_INVALID` naming the member.
5. `--from-record fixtures/gate/agrodesign/ --out <tmp>/bundle` writes a bundle that
   `verify_bundle` accepts (signature checked first), with `manifest.json` members matching
   the record's (same run id, same tree hash); the bundle's verdicts equal the record's.
6. Cross-process: two `--from-record` invocations under different `PYTHONHASHSEED` produce
   byte-identical stdout.
7. The exit code is 0 for the replayed record (all 86 decided) and 1 for a record that
   produces any `UNVERIFIED`.

## Dependencies and sequencing

Depends on cli-core (dispatch + exit codes) and render (output). Uses existing seams exactly
as the replay test does — no new engine code expected; the aspect is wiring + the cross-check
+ failure mapping. The committed `bundles/agrodesign/` (signed with the dedicated key) exists
for `verify_bundle` checks; the private key lives at `~/.ssh/plumb_bundle_ed25519` outside the
repo — tests must not depend on it (test signing needs a generated key in a tmp dir, per
`tests/bundle/bundle_helpers.py` precedent).

## Open questions / risks

- Signing in tests: `build_bundle` requires a signer; tests generate an ephemeral key pair
  with `ssh-keygen` (offline) — confirm the existing bundle helpers already do this and reuse
  them.
- The committed record's `objects/` holds 21 files, the bundle only the 7 bound outputs —
  the rebuilt bundle's member set must match `build_bundle`'s bound-outputs rule, not the
  record's full store.