"""The committed AgroDesign bundle verifies — the Phase 0 gate's evidence (signed-bundle B5).

`bundles/agrodesign/` was built by `tools/bundle_build.py` from the gate record and signed with
the project's dedicated `plumb-bundle` key; only its public key is in the repo
(`bundles/allowed_signers`). This test is what a third party runs: verify the signature,
every member, the claims' grounding in the bundled paper, and the re-derived verdicts.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from plumb.bundle import verify_bundle
from plumb.verify import DIVERGED, REPRODUCED

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "bundles" / "agrodesign"
ALLOWED = ROOT / "bundles" / "allowed_signers"


def report():
    return verify_bundle(BUNDLE, allowed_signers=ALLOWED, principal="plumb-bundle")


def test_it_verifies() -> None:
    result = report()
    assert result.ok, result.causes


def test_it_carries_the_gate_panel() -> None:
    verdicts = report().verdicts.verdicts
    assert len(verdicts) == 86
    assert Counter(v.verdict for v in verdicts) == {REPRODUCED: 85, DIVERGED: 1}


def test_its_verdicts_are_the_gate_records() -> None:
    fixture = ROOT / "fixtures" / "gate" / "agrodesign" / "verdicts.json"
    assert (BUNDLE / "verdicts.json").read_bytes() == fixture.read_bytes()


def test_it_names_the_pinned_source() -> None:
    manifest = report().manifest
    assert manifest["source"]["location"] == "https://github.com/DeepStatistix/AgroDesign.git"
    assert manifest["source"]["rev_resolved"] == "18b7c29a4f8de3dc9260b9fa42849e5a74097825"
    assert manifest["paper"]["source"] == "https://arxiv.org/pdf/2603.09041v1"
    assert manifest["signer"] == "plumb-bundle"


def test_no_private_key_is_in_the_repo() -> None:
    for path in ROOT.joinpath("bundles").rglob("*"):
        if path.is_file():
            assert b"PRIVATE KEY" not in path.read_bytes()
