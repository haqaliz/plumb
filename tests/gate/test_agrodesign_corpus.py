"""AgroDesign case #1: the real record banks, re-derives, ships pre-labeled (bank Phase 3).

Acceptance criteria 1, 2, 5 and 7 of `docs/planning/discrepancy-corpus/bank/spec.md`
on the committed gate record, in the in-process `main([...])` pattern
(`tests/cli/test_corpus_bank.py`):

1. `plumb corpus bank fixtures/gate/agrodesign --store <tmp>` writes a case whose
   members round-trip byte-identically to the record's committed bytes
   (`claims.json`, `bindings.json`, `trace.json`, `verdicts.json`;
   `nonclaims.json` == `unrepresentable.json` verbatim; every `objects/` file).
2. The banked case re-derives its verdicts from its own stored trace alone
   (`read_case` -> `parse_trace` -> `Capture` rebuild over the case's `objects/`
   -> `verify_claims`), byte-identical to the banked `verdicts.json`: 85
   `REPRODUCED`, 1 `DIVERGED`, 0 `UNVERIFIED`, 86 bound.
3. Case #1's `labels.json` carries `confirmed` for the DIVERGED claim_id, sourced
   from the owner's review (`README.md:75-82`), byte-identical to the committed
   `fixtures/gate/agrodesign/labels.json`; the manifest `has_labels` is true and
   `CaseRead.labels` round-trips it.
4. A re-bank is a no-op (exit 0, `already banked`, same case_id, bytes unchanged);
   the case_id is content-addressed and stable across stores.
5. The banked case carries no local paths (the worktree or tmp path in any text);
   no network anywhere (the autouse blocker).
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from plumb.cli import main
from plumb.corpus import read_case
from plumb.run import parse_trace
from plumb.run.capture import Capture
from plumb.verify import (
    DIVERGED,
    REPRODUCED,
    UNVERIFIED,
    Completed,
    load_bindings,
    serialize_verdicts,
    verify_claims,
)
from test_agrodesign_fixture import FIXTURE, load_claims

#: The one DIVERGED claim (`verdicts.json`: §4.1 CRD Shapiro-Wilk p, 0.034 vs 0.03455),
#: reviewed by the owner on 2026-09-27 and confirmed as a genuine reporting discrepancy.
DIVERGED_CLAIM_ID = "424724672c5a746a42bdb2a701f0ecf0c3b4d1549125aba38fad72b07c9c376a"

_WORKTREE = Path(__file__).resolve().parents[2]


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under `root`, as a posix-relative path -> bytes snapshot."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _bank(tmp_path: Path, capsys) -> Path:
    """Bank the committed gate record into a fresh store; returns the case dir."""
    store = tmp_path / "store"
    assert main(["corpus", "bank", str(FIXTURE), "--store", str(store)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    case_id = captured.out.strip().split()[1]
    assert captured.out == f"banked {case_id}\n"
    return store / case_id


def _rederive(case_dir: Path):
    """The case's own verdicts: read_case -> parse_trace -> Capture -> verify_claims."""
    case = read_case(case_dir)
    trace = parse_trace(case.members["trace"])
    capture = Capture(
        store=case_dir / "objects", artifacts=trace.artifacts, stale=trace.stale,
        causes=trace.causes,
    )
    claims = load_claims()
    bindings = load_bindings(case.members["bindings"], [c.id for c in claims])
    return case, verify_claims(claims, bindings, Completed(trace, capture))


class TestTheCaseIsTheRecordVerbatim:
    """Acceptance 1: every member round-trips the record's committed bytes."""

    def test_every_member_is_byte_identical(self, tmp_path, capsys) -> None:
        case_dir = _bank(tmp_path, capsys)
        for name in ("claims.json", "bindings.json", "trace.json", "verdicts.json"):
            assert (case_dir / name).read_bytes() == (FIXTURE / name).read_bytes()
        assert (case_dir / "nonclaims.json").read_bytes() == (
            FIXTURE / "unrepresentable.json"
        ).read_bytes()
        expected = {p.name: p.read_bytes() for p in (FIXTURE / "objects").iterdir()}
        got = {p.name: p.read_bytes() for p in (case_dir / "objects").iterdir()}
        assert got == expected


class TestTheCaseRederivesItsVerdicts:
    """Acceptance 2: the stored trace alone re-derives the banked verdicts exactly."""

    def test_rederivation_matches_the_banked_verdicts_byte_for_byte(
        self, tmp_path, capsys
    ) -> None:
        case_dir = _bank(tmp_path, capsys)
        case, verdicts = _rederive(case_dir)
        assert serialize_verdicts(verdicts) == (case_dir / "verdicts.json").read_bytes()
        assert case.case.run_id == parse_trace(case.members["trace"]).run_id

    def test_the_verdict_tally_is_85_reproduced_1_diverged(self, tmp_path, capsys) -> None:
        case_dir = _bank(tmp_path, capsys)
        case, verdicts = _rederive(case_dir)
        assert len(verdicts.verdicts) == len(load_claims()) == 86
        tally = Counter(v.verdict for v in verdicts.verdicts)
        assert tally == {REPRODUCED: 85, DIVERGED: 1}
        assert tally.get(UNVERIFIED, 0) == 0

    def test_the_divergence_is_the_labeled_claim(self, tmp_path, capsys) -> None:
        case_dir = _bank(tmp_path, capsys)
        _, verdicts = _rederive(case_dir)
        (diverged,) = [v for v in verdicts.verdicts if v.verdict == DIVERGED]
        assert diverged.claim_id == DIVERGED_CLAIM_ID
        assert diverged.review_required


class TestLabelsAreTransported:
    """Acceptance 5: the owner's review banks as the case's labels, byte-identically."""

    def test_the_committed_labels_map_the_diverged_claim_to_confirmed(self) -> None:
        labels = json.loads((FIXTURE / "labels.json").read_text(encoding="utf-8"))
        assert labels == {DIVERGED_CLAIM_ID: "confirmed"}

    def test_the_case_carries_the_committed_labels_byte_for_byte(
        self, tmp_path, capsys
    ) -> None:
        case_dir = _bank(tmp_path, capsys)
        assert (case_dir / "labels.json").read_bytes() == (
            FIXTURE / "labels.json"
        ).read_bytes()
        document = json.loads((case_dir / "case.json").read_bytes())
        assert document["has_labels"] is True
        assert read_case(case_dir).labels == {DIVERGED_CLAIM_ID: "confirmed"}


class TestRebankIsANoop:
    """Acceptance 1/exit contract: a re-bank exits 0 and touches nothing."""

    def test_rebank_is_a_no_op_with_the_same_case_id(self, tmp_path, capsys) -> None:
        store = tmp_path / "store"
        assert main(["corpus", "bank", str(FIXTURE), "--store", str(store)]) == 0
        case_id = capsys.readouterr().out.strip().split()[1]
        snapshot = _tree_bytes(store)
        code = main(["corpus", "bank", str(FIXTURE), "--store", str(store)])
        assert code == 0
        captured = capsys.readouterr()
        assert captured.out == f"already banked: {case_id}\n"
        assert captured.err == ""
        assert _tree_bytes(store) == snapshot


class TestTheCaseIdIsContentAddressed:
    """The case_id derives from the record's bytes, not the store's location."""

    def test_the_case_id_is_stable_across_two_stores(self, tmp_path, capsys) -> None:
        case_dir = _bank(tmp_path, capsys)
        other = tmp_path / "elsewhere"
        assert main(["corpus", "bank", str(FIXTURE), "--store", str(other)]) == 0
        captured = capsys.readouterr()
        assert captured.out == f"banked {case_dir.name}\n"
        assert (other / case_dir.name).is_dir()


class TestNoLocalPaths:
    """Acceptance 7: the banked case carries no path from this machine."""

    def test_the_banked_case_carries_no_local_paths(self, tmp_path, capsys) -> None:
        case_dir = _bank(tmp_path, capsys)
        for path in case_dir.rglob("*"):
            if path.is_file() and path.suffix != ".pdf":
                text = path.read_bytes().decode("utf-8", "replace")
                assert str(_WORKTREE) not in text, f"{path.name} carries the worktree path"
                assert str(tmp_path) not in text, f"{path.name} carries a temp path"