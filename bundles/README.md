# Signed bundles

Evidence a third party can check without trusting this repo. Format and checks:
`src/plumb/bundle/` (C6); design: `docs/planning/signed-bundle/prd.md`.

| Path | What it is |
|---|---|
| `allowed_signers` | the public key of the project's dedicated `plumb-bundle` Ed25519 signing key (OpenSSH allowed-signers format). The private key is not in the repo. |
| `agrodesign/` | the Phase 0 gate bundle — AgroDesign, arXiv:2603.09041 (built from `fixtures/gate/agrodesign/` by `tools/bundle_build.py`) |

Each bundle is a directory: `manifest.json` lists every other member by path, SHA-256 and size,
and `manifest.sig` is an SSHSIG (`ssh-keygen -Y`, namespace `plumb-bundle-v1`) over the
manifest's exact bytes. Bundles carry no timestamp by default, so the same inputs and key give
the same bytes; `build_bundle(created=...)` adds an optional signed `created` field when a
builder wants one.

## Checking a bundle from the shell

```bash
plumb bundle verify bundles/agrodesign --allowed-signers bundles/allowed_signers
plumb bundle inspect bundles/agrodesign            # declared fields; signature not checked
plumb bundle pack bundles/agrodesign --out agrodesign.tar.gz   # deterministic bytes
plumb bundle verify agrodesign.tar.gz --allowed-signers bundles/allowed_signers
```

`verify` exits 1 with one line per named cause when the bundle does not hold. Archives are
untrusted input: unpacking refuses absolute paths, `..`, links and devices.

## Checking the AgroDesign bundle

**Offline — is the bundle what it says?** Checks the signature, every member's hash, that every
claim is written verbatim in the bundled paper (re-admitted through the admission gate), and
that the verdicts re-derive byte for byte from the bundled outputs:

```python
from plumb.bundle import verify_bundle
report = verify_bundle("bundles/agrodesign", allowed_signers="bundles/allowed_signers",
                       principal="plumb-bundle")
assert report.ok   # 86 verdicts: 85 REPRODUCED, 1 DIVERGED
```

Or with OpenSSH alone, for the signature:
`ssh-keygen -Y verify -f bundles/allowed_signers -I plumb-bundle -n plumb-bundle-v1 -s bundles/agrodesign/manifest.sig < bundles/agrodesign/manifest.json`

**Networked — did those numbers come from that code?**
`uv run tools/bundle_replay.py bundles/agrodesign bundles/allowed_signers plumb-bundle` clones
the repository at the signed commit, checks its tree hash, installs the exact frozen versions
(`--no-deps`, Python 3.12.13), re-runs the recorded command, and compares output hashes.

## Run replay, 2026-09-27

```
bundle_run_id  96646995704bf25c83f5e0393359845f09c4d959bae5f036410821b14fa567b1
fresh_run_id   96646995704bf25c83f5e0393359845f09c4d959bae5f036410821b14fa567b1
python 3.12.13, 21 pinned packages, run_failure: none
result: RUN_REPLAYED
```

The run id covers the command, the tree hash and every locatable output's hash, so equal ids
mean every output of the fresh run is byte-identical to the bundled one. The bundle was also
verified from a fresh `git clone` of this repository (hash-listed files are marked binary in
`.gitattributes`, so a checkout never rewrites a byte).

## What the bundle does and does not claim

It shows that the paper's own code, at the pinned commit and in the frozen environment,
produces the bundled outputs, and that 85 of the paper's 86 rule-defined claims hold against
them within the paper's written precision; one (`§4.1` Shapiro-Wilk p, reported 0.034, computed
0.03455) does not. That is a discrepancy against the paper's own artifact, flagged
`review_required` — not a statement that the paper's conclusions are wrong, and not a
misconduct claim. The owner reviewed it on 2026-09-27 and confirmed it as a genuine reporting
discrepancy; the review is recorded here rather than inside the signed bundle, which is
unchanged. The bundle has not been published or sent to the author.

## Key rotation

`allowed_signers` is line-based and the verifier's file is the trust anchor: a rotated file may
list a retired key and the current one, and a bundle signed by either verifies. Retiring a key
means deleting its line, after which its bundles report `SIGNATURE_INVALID`. The project's own
key is `plumb-bundle`; a rotation replaces the line in `bundles/allowed_signers` and re-signs
`agrodesign/` with the new key (`tools/bundle_build.py`), keeping the old bundles' history in
git.

## Known gaps

- **Timestamps are self-asserted.** `created` is signed by the same key, so it proves nothing to
  someone who does not trust the signer's clock — it is not an RFC 3161 third-party timestamp.
- **No transparency log / sigstore.** These need a third-party service and a crypto dependency;
  the bundle design is zero-dependency on purpose, and feature-detected, untested integration
  would be worse than a named gap. Add one when a consumer asks for public inclusion proofs.
