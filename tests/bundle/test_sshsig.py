"""SSHSIG signing via `ssh-keygen -Y` (signed-bundle B2, PRD B1).

No crypto dependency: OpenSSH signs and verifies. Pinned: a good signature verifies; Ed25519
SSHSIG is deterministic (the bundle's bytes must be reproducible, signature included); every
way a signature can be wrong — another key, another principal, another namespace, changed
data, empty or garbage bytes — is a named reason, never an exception.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plumb.bundle.sshsig import NAMESPACE, SshSigner, ssh_verify

DATA = b'{"format":"plumb-bundle/1"}\n'


def test_the_namespace_is_pinned() -> None:
    assert NAMESPACE == "plumb-bundle-v1"


def test_a_good_signature_verifies(signing_key) -> None:
    key, allowed = signing_key
    signature = SshSigner(key, "plumb-test").sign(DATA)
    assert signature.startswith(b"-----BEGIN SSH SIGNATURE-----")
    assert ssh_verify(DATA, signature, allowed_signers=allowed, principal="plumb-test") is None


def test_signing_is_deterministic(signing_key) -> None:
    signer = SshSigner(signing_key[0], "plumb-test")
    assert signer.sign(DATA) == signer.sign(DATA)


def test_changed_data_fails(signing_key) -> None:
    key, allowed = signing_key
    signature = SshSigner(key, "plumb-test").sign(DATA)
    assert ssh_verify(DATA + b" ", signature, allowed_signers=allowed, principal="plumb-test")


def test_another_key_fails(signing_key, other_key) -> None:
    signature = SshSigner(other_key[0], "plumb-test").sign(DATA)
    assert ssh_verify(DATA, signature, allowed_signers=signing_key[1], principal="plumb-test")


def test_another_principal_fails(signing_key) -> None:
    key, allowed = signing_key
    signature = SshSigner(key, "plumb-test").sign(DATA)
    assert ssh_verify(DATA, signature, allowed_signers=allowed, principal="someone-else")


def test_another_namespace_fails(signing_key, tmp_path: Path) -> None:
    import subprocess

    key, allowed = signing_key
    (tmp_path / "data").write_bytes(DATA)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", "git", str(tmp_path / "data")],
                   check=True, capture_output=True)
    signature = (tmp_path / "data.sig").read_bytes()
    assert ssh_verify(DATA, signature, allowed_signers=allowed, principal="plumb-test")


@pytest.mark.parametrize("signature", [b"", b"not a signature", b"\xff" * 64])
def test_garbage_fails_with_a_reason(signing_key, signature: bytes) -> None:
    reason = ssh_verify(DATA, signature, allowed_signers=signing_key[1], principal="plumb-test")
    assert isinstance(reason, str) and reason


def test_a_missing_key_raises_on_sign(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        SshSigner(tmp_path / "absent", "plumb-test").sign(DATA)
