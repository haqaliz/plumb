"""Offline replay of the AgroDesign gate verdicts (gate-paper G4, PRD M5).

`tools/gate_run.py` ran the paper's own code once, at dev time, through the real spine and
committed what C4 needs to decide: the trace, the locatable captured outputs (by SHA-256),
and the verdicts. This test re-derives every verdict from those committed bytes alone — no
network, no environment, no run — and asserts they are byte-identical to `verdicts.json`.

It does not re-run the paper's code; that is C6's run-level replay, not built. What it pins is
that the verdicts are a pure function of the committed evidence.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from plumb.run import parse_trace
from plumb.run.capture import Capture
from plumb.verify import (
    DIVERGED,
    REPRODUCED,
    Completed,
    load_bindings,
    serialize_verdicts,
    verify_claims,
)
from test_agrodesign_fixture import FIXTURE, load_claims

LOCAL_PATH_MARKERS = ("/Users/", "/home/", "/private/", "/tmp/", "/var/folders/", "C:\\")


def replay():
    claims = load_claims()
    bindings = load_bindings((FIXTURE / "bindings.json").read_bytes(), [c.id for c in claims])
    trace = parse_trace((FIXTURE / "trace.json").read_bytes())
    capture = Capture(
        store=FIXTURE / "objects", artifacts=trace.artifacts, stale=trace.stale,
        causes=trace.causes,
    )
    return claims, verify_claims(claims, bindings, Completed(trace, capture))


def test_the_verdicts_replay_byte_for_byte() -> None:
    _, verdicts = replay()
    assert serialize_verdicts(verdicts) == (FIXTURE / "verdicts.json").read_bytes()


def test_every_committed_object_is_a_locatable_output_under_its_own_hash() -> None:
    trace = parse_trace((FIXTURE / "trace.json").read_bytes())
    locatable = {a.sha256 for a in trace.artifacts if not a.diagnostic_only}
    committed = {p.name for p in (FIXTURE / "objects").iterdir()}
    assert committed == locatable
    for path in (FIXTURE / "objects").iterdir():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == path.name


def test_the_run_succeeded_on_a_pinned_git_tree() -> None:
    trace = parse_trace((FIXTURE / "trace.json").read_bytes())
    assert trace.failure is None and trace.exit_code == 0
    assert trace.causes == ()
    assert trace.tree_hash.scheme == "git-tree"
    # The repo's committed input datasets predate the run: recorded stale, never read, unbound.
    datasets = {f"src/agrodesign/datasets/data/{name}.csv" for name in (
        "crd", "factorial", "grouped", "gxe", "mixed", "multitrait", "rcbd", "splitplot")}
    assert {s.relpath for s in trace.stale} == datasets
    bindings = json.loads((FIXTURE / "bindings.json").read_text(encoding="utf-8"))["bindings"]
    assert not datasets & {b["artifact"] for b in bindings}
    assert trace.entrypoint_source == "explicit"


def test_the_verdict_tally() -> None:
    claims, verdicts = replay()
    assert len(verdicts.verdicts) == len(claims) == 86
    assert Counter(v.verdict for v in verdicts.verdicts) == {REPRODUCED: 85, DIVERGED: 1}


def test_the_one_divergence_is_the_crd_shapiro_wilk_p() -> None:
    claims, verdicts = replay()
    by_id = {c.id: c for c in claims}
    (diverged,) = [v for v in verdicts.verdicts if v.verdict == DIVERGED]
    assert by_id[diverged.claim_id].metric == "§4.1 CRD Shapiro-Wilk p (prose)"
    assert (diverged.reported_text, diverged.located_text) == ("0.034", "0.03455")
    assert diverged.review_required


def test_no_committed_file_carries_a_local_path() -> None:
    for path in FIXTURE.rglob("*"):
        if path.is_file() and path.suffix != ".pdf":
            text = path.read_bytes().decode("utf-8", "replace")
            for marker in LOCAL_PATH_MARKERS:
                assert marker not in text, f"{path.name} contains {marker}"


def test_every_binding_names_a_curated_claim() -> None:
    ids = {c.id for c in load_claims()}
    bindings = json.loads((FIXTURE / "bindings.json").read_text(encoding="utf-8"))["bindings"]
    assert {b["claim_id"] for b in bindings} == ids
