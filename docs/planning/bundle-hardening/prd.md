# PRD — bundle hardening: CLI, packaging, timestamps, rotation

Issue: #20. Closes four of the five named C6 gaps (`docs/technical/CAPABILITY_ROADMAP.md:320`).

## Requirements

- **R1 — `plumb bundle verify <bundle> --allowed-signers FILE [--principal P] [--paper FILE]
  [--json]`.** Prints one line per named cause on stderr and exits 1 when the bundle does not
  verify; exits 0 and prints a one-line summary when it does. Never a traceback.
- **R2 — `plumb bundle inspect <bundle> [--json]`.** Prints format, signer, paper hash, tree
  hash, run id, `created` (or `none`), member count, and explicitly that the signature was not
  checked. Read-only, works on a directory or an archive.
- **R3 — `plumb bundle pack <bundle> --out FILE`.** Writes a deterministic archive: entries
  sorted, mtime 0, uid/gid 0, no uname/gname, normalised modes. Two packs of the same bundle are
  byte-identical. `.tar` and `.tar.gz` both supported.
- **R4 — archives are accepted by `verify` and `inspect`.** Unpacking refuses absolute paths,
  `..`, links and devices, with a named cause and exit 1 — never a write outside the temp dir.
- **R5 — optional signed `created`.** `build_bundle(..., created="2026-10-21T00:00:00Z")` puts the
  field inside the signed manifest; older manifests without it still verify. Documented as
  self-asserted: the signer controls the clock, so it proves ordering only against someone who
  trusts the signer.
- **R6 — rotation is proven, not built.** A test verifies a bundle against an `allowed_signers`
  holding a retired key and the current key; docs describe retiring a key as deleting its line.

## Non-goals

- Transparency log / sigstore: deferred, reason documented in `bundles/README.md`.
- Third-party RFC 3161 timestamps.

## Acceptance

New tests in `tests/bundle/test_pack.py` and `tests/cli/test_bundle_cli.py`; the committed
AgroDesign bundle still verifies unmodified; `uv run pytest -q` green, offline.
