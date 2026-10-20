"""The published-finding note matches its bundle (issue #25).

A finding is only as good as its evidence: the note's numbers, claim id and replay command must be
the ones the signed bundle actually carries. This test is that check, so the note cannot drift
into a claim the bundle does not support.
"""

from __future__ import annotations

from pathlib import Path

from plumb.bundle import verify_bundle
from plumb.verify import DIVERGED

ROOT = Path(__file__).resolve().parents[2]
NOTE = ROOT / "docs" / "findings" / "agrodesign.md"
BUNDLE = ROOT / "bundles" / "agrodesign"
ALLOWED = ROOT / "bundles" / "allowed_signers"
CLAIM_ID = "424724672c5a746a42bdb2a701f0ecf0c3b4d1549125aba38fad72b07c9c376a"


def _note() -> str:
    return NOTE.read_text(encoding="utf-8")


def _diverged():
    report = verify_bundle(BUNDLE, allowed_signers=ALLOWED, principal="plumb-bundle")
    assert report.ok, report.causes
    (verdict,) = [v for v in report.verdicts.verdicts if v.verdict == DIVERGED]
    return verdict


def test_the_note_names_the_bundles_only_divergence() -> None:
    verdict = _diverged()
    assert verdict.claim_id == CLAIM_ID
    text = _note()
    assert CLAIM_ID in text
    assert verdict.reported_text in text
    assert verdict.located_text in text
    assert str(verdict.delta) in text


def test_the_replay_commands_are_the_ones_the_repo_documents() -> None:
    text = _note()
    assert "verify_bundle('bundles/agrodesign'" in text
    assert "tools/bundle_replay.py bundles/agrodesign" in text


def test_the_note_does_not_claim_publication_or_contact() -> None:
    text = _note()
    assert "not published, not sent to the authors" in text
    assert "- [ ] Owner sign-off to publish." in text
    assert "- [x]" not in text


def test_the_note_frames_it_as_a_discrepancy_not_misconduct() -> None:
    text = _note()
    assert "misconduct claim" in text
    assert "does **not** assert that the analysis is wrong" in text
