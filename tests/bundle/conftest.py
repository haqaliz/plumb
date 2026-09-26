"""Throwaway Ed25519 keys for the bundle tests: generated locally, never the owner's.

`ssh-keygen` is a local subprocess — no network — and each key lives in a pytest tmp dir.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


def make_key(directory: Path, name: str, principal: str) -> tuple[Path, Path]:
    """A passphrase-less Ed25519 key and an allowed-signers file naming `principal`."""
    key = directory / name
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", principal, "-f", str(key)],
        check=True, capture_output=True,
    )
    allowed = directory / f"{name}.allowed_signers"
    allowed.write_text(f"{principal} {(directory / (name + '.pub')).read_text().strip()}\n")
    return key, allowed


@pytest.fixture(scope="session")
def signing_key(tmp_path_factory) -> tuple[Path, Path]:
    return make_key(tmp_path_factory.mktemp("keys"), "signer", "plumb-test")


@pytest.fixture(scope="session")
def other_key(tmp_path_factory) -> tuple[Path, Path]:
    return make_key(tmp_path_factory.mktemp("other-keys"), "stranger", "plumb-test")
