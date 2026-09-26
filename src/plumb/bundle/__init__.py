"""C6 signed replayable bundle: evidence a third party can check without trusting us.

`build_bundle` writes a directory — a canonical `manifest.json` listing every member by path,
SHA-256 and size, its detached SSHSIG `manifest.sig` (`ssh-keygen -Y`, no crypto dependency),
the claims, bindings, run trace, verdicts and frozen environment, and only the captured
outputs a binding reads — and refuses to sign anything that would not verify.
`verify_bundle` checks, in order, the signature, the manifest, the members, the structure,
refused content, the claims' grounding in the paper, and the re-derived verdicts, and reports
named causes (`plumb.bundle.causes`).

**Verdicts are re-derived, never trusted.** A bundle's verdicts are recomputed by C4 from its
own signed outputs, and its claims are re-admitted against the paper through the admission
gate — so a bundle cannot carry a claim the paper does not make, or a verdict its evidence
does not produce. A failing bundle is not evidence; its causes are never verdicts.

| Cause | When |
|---|---|
| `SIGNATURE_MISSING` | no `manifest.sig` |
| `SIGNATURE_INVALID` | not the verifier's trusted principal's signature over these manifest bytes |
| `MANIFEST_INVALID` | not a readable bundle, a member that does not parse, a mismatched trace, a bound output left out |
| `MEMBER_MISSING` / `MEMBER_TAMPERED` / `MEMBER_UNLISTED` | a listed file absent / not its hash / a file not listed |
| `MEMBER_REFUSED` | a local path, stderr, an output the run did not produce, a symlink |
| `PAPER_MISSING` / `PAPER_MISMATCH` | no paper to ground the claims on / not the bundle's paper |
| `CLAIMS_UNGROUNDED` | a claim does not re-admit against the paper at its span |
| `VERDICTS_MISMATCH` | the re-derived verdicts are not the signed ones |
"""

from __future__ import annotations

from plumb.bundle.build import build_bundle, rebuild_bundle
from plumb.bundle.causes import BUNDLE_CAUSES, BundleRefused
from plumb.bundle.sshsig import NAMESPACE, SshSigner, ssh_verify
from plumb.bundle.verify import FORMAT, BundleReport, verify_bundle

__all__ = [
    "BUNDLE_CAUSES",
    "FORMAT",
    "NAMESPACE",
    "BundleRefused",
    "BundleReport",
    "SshSigner",
    "build_bundle",
    "rebuild_bundle",
    "ssh_verify",
    "verify_bundle",
]
