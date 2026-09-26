"""Detached signatures with `ssh-keygen -Y` (OpenSSH SSHSIG) — no crypto dependency.

`SshSigner(key_path, principal).sign(data)` returns an armored SSHSIG over `data` in the
pinned namespace; `ssh_verify(data, signature, allowed_signers=..., principal=...)` returns
`None` for a good signature and the reason otherwise. OpenSSH ≥ 8.1 is required on both sides.

**Trust is the verifier's.** `allowed_signers` (OpenSSH's own format: `principal key`) is the
file the *verifier* chose; the principal is the identity they expect. A bundle names its
signer, but that name is only informational — it is checked against the verifier's file.

**Deterministic.** Ed25519 signatures are deterministic, and the SSHSIG envelope adds no
timestamp or nonce, so the same key over the same bytes gives the same signature — a bundle
is byte-reproducible, signature included.

**No shell.** Every call is a fixed argv; data goes through a private temp dir (sign) or
stdin (verify). The namespace keeps a bundle signature from being replayed as, say, a git
commit signature, and the other way round.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

__all__ = ["NAMESPACE", "SshSigner", "ssh_verify"]

NAMESPACE = "plumb-bundle-v1"
_TIMEOUT_SECONDS = 60


class SshSigner:
    """Signs bytes with one OpenSSH private key, under the bundle namespace."""

    def __init__(self, key_path: Path | str, principal: str) -> None:
        self.key_path = Path(key_path)
        self.principal = principal

    def sign(self, data: bytes) -> bytes:
        with tempfile.TemporaryDirectory(prefix="plumb-sign-") as tmp:
            target = Path(tmp) / "manifest"
            target.write_bytes(data)
            result = subprocess.run(
                ["ssh-keygen", "-Y", "sign", "-f", str(self.key_path), "-n", NAMESPACE,
                 str(target)],
                capture_output=True, timeout=_TIMEOUT_SECONDS, check=False,
            )
            signature = target.with_name("manifest.sig")
            if result.returncode != 0 or not signature.is_file():
                detail = result.stderr.decode("utf-8", "replace").strip()
                raise RuntimeError(f"ssh-keygen could not sign with {self.key_path}: {detail}")
            return signature.read_bytes()


def ssh_verify(
    data: bytes, signature: bytes, *, allowed_signers: Path | str, principal: str
) -> str | None:
    """`None` if `signature` is `principal`'s over `data` in the namespace; else why not."""
    with tempfile.TemporaryDirectory(prefix="plumb-verify-") as tmp:
        sig_path = Path(tmp) / "manifest.sig"
        sig_path.write_bytes(signature)
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers), "-I", principal,
             "-n", NAMESPACE, "-s", str(sig_path)],
            input=data, capture_output=True, timeout=_TIMEOUT_SECONDS, check=False,
        )
    if result.returncode == 0:
        return None
    detail = (result.stderr or result.stdout).decode("utf-8", "replace").strip()
    return detail.splitlines()[0] if detail else f"ssh-keygen exited {result.returncode}"
