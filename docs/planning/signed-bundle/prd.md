# PRD — C6 signed replayable bundle, first slice (`signed-bundle`)

Source: `docs/planning/_card/issue.md` (inline brief from `plumb-next`) and
`docs/planning/_card/understanding.md` (deep dig + signing spike). Decisions B1–B7 are
recommendations for approval at the review gate.

**Status (2026-09-27): landed.** The AgroDesign bundle verifies (also from a fresh clone) and its
run replayed byte-identical from a clean clone. **One change from B3, forced by a guardrail:**
reading claims back could not construct `Claim`s outside the admission gate
(`test_admit.py`), so `parse_claims` returns records and `readmit` re-admits them against the
paper — which makes the paper **required at verification** (bundled, or supplied and checked
against its SHA-256). The committed AgroDesign bundle includes it (CC BY). Gate conditions: 1 and
2 met; 3 (owner review of the `DIVERGED`) outstanding.

## Problem Statement

Plumb has produced its first real-paper panel (AgroDesign: 86 bound, 85 `REPRODUCED`,
1 `DIVERGED`), but nobody outside this repo can check it. "A finding nobody can independently
replay is an opinion" (`CAPABILITY_ROADMAP.md` C6). The Phase 0 gate needs exactly this, and
R4 (legal/ethical) says a finding may only ever be shared *with* its bundle — so C6 also gates
the owner's decision about contacting AgroDesign's author.

## Goals & Success Metrics

- **G1** — `build_bundle` writes a signed bundle for the AgroDesign record; `verify_bundle`
  accepts it offline and re-derives all 86 verdicts byte-identical to the signed
  `verdicts.json`.
- **G2** — Every tampering class fails with a **named** bundle cause (test per cause); none is
  a silent pass, none raises an unhandled exception.
- **G3** — Deterministic: building twice (two processes) gives byte-identical bundles,
  signature included.
- **G4** — A run-level replay from a clean clone reproduces the bundle's output hashes (run
  once, by hand, networked), or reports exactly which outputs differ.

## Decisions (recommended)

- **B1 — Signing: `ssh-keygen -Y sign` / `verify`, Ed25519, namespace `plumb-bundle-v1`**, a
  detached SSHSIG `manifest.sig` over the exact bytes of `manifest.json`. No new dependency
  (pypdf stays the only one); OpenSSH ≥ 8.1 on both sides, and its version is recorded. The
  signer is an injectable seam; tests generate a throwaway key in a tmp dir (a local
  subprocess, no network). **Trust is the verifier's decision**: `verify_bundle` takes an
  `allowed_signers` file and a principal; the principal the manifest names is informational.
  Sigstore-style transparency is a later slice (it needs network and an identity provider).
- **B2 — The bundle is a directory**, each member named by its role:

  | Member | Content |
  |---|---|
  | `manifest.json` | canonical JSON: `format: "plumb-bundle/1"`, paper identity, repo source + tree hash, `run_id`, signer principal, and every other member's `{path, sha256, size}`, sorted |
  | `manifest.sig` | the SSHSIG over `manifest.json` |
  | `claims.json` | `serialize_claims(claims, paper_hash=…)` |
  | `bindings.json` | the bindings file exactly as used (its bytes are what bound) |
  | `trace.json` | `serialize_trace` |
  | `objects/<sha256>` | the captured outputs **the bindings read** — nothing else |
  | `verdicts.json` | `serialize_verdicts` |
  | `environment.txt` | the frozen environment the run used |

  No tarball in this slice. No timestamp anywhere (it would break G3). The format string is
  the one version stamp.
- **B3 — Minimal disclosure (constraint #2).** Only bound objects are members; the trace still
  lists every output's hash, so the run id stays checkable. The paper PDF is **not** a member
  by default — it is identified by its SHA-256, the C1 paper hash, and its source URL;
  `include_paper=True` adds it (fine for CC BY; the user's choice).
- **B4 — Build refuses what verify would refuse.** `build_bundle` runs the same checks before
  signing: no absolute or run-side path in any member, no stderr object, every object is a
  locatable artifact of the trace, every binding's claim is in the claim set, and the
  verdicts re-derive byte-identical. A bundle that would not verify is never signed.
- **B5 — Verify is ordered and never trusts an unsigned byte.** Signature first; if it fails,
  stop (`SIGNATURE_INVALID`, the manifest is not read further). Then members: every listed
  member exists with its hash and size, no unlisted file (`MEMBER_MISSING`, `MEMBER_TAMPERED`,
  `MEMBER_UNLISTED`), no absolute path or stderr (`MEMBER_REFUSED`). Then structure
  (`MANIFEST_INVALID`: parse failures, claim ids that do not recompute, a trace whose run id
  does not match). Then re-derivation (`VERDICTS_MISMATCH`). The result is a report with named
  causes; content problems never raise.
- **B6 — Run replay is a `tools/` script, never a test.** `tools/bundle_replay.py <bundle>`:
  clone the repo at the manifest's rev, check the tree hash (else stop: `TREE_MISMATCH`),
  build a venv with the recorded python and `uv pip install --no-deps` of the exact frozen
  pins plus the checkout, run the trace's argv through C3, and compare the fresh locatable
  output hashes with the bundle's. Same hashes → "run replayed". Different → it re-derives the
  verdicts on the fresh outputs and reports each changed claim as **`UNVERIFIED` (drift)**, never
  as a new `DIVERGED` — the bundle's verdicts are not rewritten.
- **B7 — The committed AgroDesign bundle** lives at `bundles/agrodesign/`, built from
  `fixtures/gate/agrodesign/`. **Signing key: owner decision.** Recommended: a dedicated
  Ed25519 key `plumb-bundle` created by the owner (or by me, with the owner's OK) outside the
  repo, with only its public key committed as `bundles/allowed_signers`. Never the owner's
  personal SSH key, and never a private key in the repo.

## Requirements

### Must-have

- **M1 `parse_claims`** — inverse of `serialize_claims`: round trip is the identity; each
  claim's id is recomputed and must equal the serialized id; unknown variants refused.
- **M2 `build_bundle(out_dir, *, claims, paper_hash, paper_identity, bindings_bytes, trace,
  capture, verdicts_bytes, environment, source, signer)`** with B2–B4.
- **M3 `sign` / `verify` via `ssh-keygen -Y`** behind a seam; namespace pinned; subprocess
  never gets a shell.
- **M4 `verify_bundle(dir, *, allowed_signers, principal) -> BundleReport`** with B5; the
  report carries the re-derived `VerdictSet` when everything passes.
- **M5 Tests** (offline): a synthetic-run bundle round-trips; one test per bundle cause (flip a
  byte in each member kind, delete one, add one, wrong key, wrong principal, wrong namespace,
  missing signature, absolute path, stderr object); two-process byte identity; the committed
  AgroDesign bundle verifies against the committed `allowed_signers`.
- **M6 The AgroDesign bundle** committed (B7).

### Should-have

- **S1** `tools/bundle_replay.py` (B6), run once by hand on the AgroDesign bundle. Replay
  happens *after* signing, so its result cannot live inside the signed directory (an extra file
  there is `MEMBER_UNLISTED`): it is recorded in `bundles/README.md`, beside the bundle. Layout:
  `bundles/README.md`, `bundles/allowed_signers`, `bundles/agrodesign/` (the bundle).
- **S2** Docs: `ARCHITECTURE.md` (C6 status; signing open question resolved), `CAPABILITY_ROADMAP.md`,
  `ROADMAP.md` (gate status per below), `CLAUDE.md`, `README.md`.

## Gate status (what this PR may claim)

Phase 0 gate: *real reproducible panel + replayable bundle*. After this PR, the docs may say
**"gate met"** only if all three hold: (1) the AgroDesign bundle is signed with the owner's
bundle key and verifies; (2) `tools/bundle_replay.py` reproduced the output hashes from a
clean clone; (3) the owner has reviewed the one `DIVERGED` (R2's human-in-the-loop). Otherwise
the docs state which of the three is outstanding.

## Technical Considerations

- **C6**, `src/plumb/bundle/`; consumes C1 (`serialize_claims`, new `parse_claims`), C3
  (`serialize_trace`, `parse_trace`, `Capture`), C4 (`load_bindings`, `verify_claims`,
  `serialize_verdicts`). Standard library + the `ssh-keygen` binary.
- **Verdict impact:** none new — verify re-runs C4 on signed evidence; replay drift is reported
  as `UNVERIFIED`, never `DIVERGED` (constraint #3).
- **Determinism:** canonical JSON everywhere, sorted members, no clocks; Ed25519 SSHSIG is
  deterministic (spike).

## Risks & Open Questions

- **R2 — replay drift.** No lockfile upstream; the frozen pins are the mitigation, and a
  mismatch is `UNVERIFIED`. PyPI could in principle yank a pinned version — recorded, not
  solved.
- **Key management** — a lost private key means no new signatures, but existing bundles still
  verify; key rotation is a follow-on.
- **`ssh-keygen` availability** — standard on macOS/Linux; Windows ships OpenSSH but untested
  here.
- **Open:** B7's key (owner).

## Self-critique (prd-generator, 2026-09-27)

| Dimension | Rating | Note |
|---|---|---|
| Problem | 🟢 | The gate's last criterion, and R4's precondition for any disclosure |
| Metrics | 🟢 | Each goal is a test or a committed artifact |
| Scope | 🟢 | Directory bundle, SSHSIG, no transparency log |
| Risks | 🟡 | Run replay depends on PyPI keeping the pinned versions |
| Verdict honesty | 🟢 | Replay drift is `UNVERIFIED`; verify never trusts an unsigned byte |
| Feasibility | 🟢 | Signing spiked; loaders exist or are small (`parse_claims`) |
| Fixed | — | S1 put the post-signing replay result inside the signed directory — moved beside it |

**Hard question:** a signature proves *who* vouches for the bundle, not that the run was honest.
A third party who trusts neither Plumb nor its owner must still re-run (B6). Is the gate's
"bundle a third party can replay" satisfied by the verdict-level replay alone, or only once a
run-level replay has succeeded from a clean clone? This PRD takes the stricter reading.

## Out of Scope

Sigstore/transparency logs, timestamps, tar/zip packaging, key rotation, a `plumb bundle` CLI,
publishing the bundle anywhere, contacting the author.
