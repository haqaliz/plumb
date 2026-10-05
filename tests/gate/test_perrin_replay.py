"""Offline replay of the Perrin gate verdicts (panel-run P2).

`tools/perrin_gate_run.py` ran the paper's own code once, at dev time, through the real
spine (env built at the recorded `--exclude-newer 2024-06-18` boundary — the earliest
buildable on this machine) and committed what C4 needs to decide: the trace, the locatable
captured outputs (by SHA-256), and the verdicts. This test re-derives every verdict from
those committed bytes alone — no network, no environment, no run — and asserts they are
byte-identical to `verdicts.json`. It does not re-run the paper's code; that is C6's
run-level replay, not built.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import pytest

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
from test_perrin_fixture import FIXTURE, load_claims

LOCAL_PATH_MARKERS = ("/Users/", "/home/", "/private/", "/tmp/", "/var/folders/", "C:\\")

REV = "76ce145f42fd37a91b389d8c8762de167647f82f"


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


def test_the_run_succeeded_on_the_pinned_git_tree() -> None:
    trace = parse_trace((FIXTURE / "trace.json").read_bytes())
    assert trace.failure is None and trace.exit_code == 0
    assert trace.causes == ()
    assert trace.tree_hash.scheme == "git-tree"
    # The repo's committed inputs (DGP configs + ARR grids) predate the run: recorded
    # stale, never read, unbound. Pinned exactly — the fixture is committed, so the set
    # is stable.
    assert {s.relpath for s in trace.stale} == _STALE_INPUTS
    bindings = json.loads((FIXTURE / "bindings.json").read_text(encoding="utf-8"))["bindings"]
    assert not _STALE_INPUTS & {b["artifact"] for b in bindings}
    assert trace.entrypoint_source == "explicit"
    assert REV in (FIXTURE / "source.json").read_text(encoding="utf-8")


#: The committed inputs the run's imports touched (freshness-guarded, never bound).
_STALE_INPUTS = frozenset({
    "hte/configs/data_configs/dim1000_isotropic_pro(+)10_pro(-)10_noise480.json",
    "hte/configs/data_configs/dim1000_isotropic_pro(+)10_pro(-)10_noise500.json",
    "hte/configs/data_configs/dim100_isotropic_pro(+)5_pro(-)5_noise50.json",
    "hte/configs/data_configs/dim20_isotropic_pro(+)5_pro(-)5.json",
    "hte/configs/data_configs/gamma_semi_synthetic_p1000.json",
    "hte/configs/data_configs/semi_synthetic_p1000.csv",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=1000_range=[-10.0,10.0]_nb=500_group=[dim1000_pred4_prog0_balanced]_August_08_04_2023_02:31:57.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=1000_range=[-10.0,10.0]_nb=500_group=[semi_synth_sbg_1000]_October_10_11_2023_14:12:08.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=100_range=[-10.0,10.0]_nb=500_group='dim100_pred3_prog2_balanced'_July_07_24_2023_15:54:00.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=100_range=[-10.0,10.0]_nb=500_group='dim100_pred4_prog2_balanced'_July_07_26_2023_10:32:59.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=100_range=[-10.0,10.0]_nb=500_group=[dim100_pred4_prog0_balanced]_July_07_25_2023_16:08:59.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=100_range=[-10.0,10.0]_nb=500_group=[dim100_pred4_prog4_balanced]_July_07_25_2023_12:05:03.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=20_range=[-10.0,10.0]_nb=500_group=[dim20_pred4_prog0_balanced]_July_07_12_2023_15:15:24.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=20_range=[-10.0,10.0]_nb=500_group=[dim20_pred4_prog1_balanced]_September_09_18_2023_16:42:32.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=20_range=[-10.0,10.0]_nb=500_group=[dim20_pred4_prog2_balanced]_July_07_19_2023_15:05:13.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=20_range=[-10.0,10.0]_nb=500_group=[dim20_pred4_prog3_balanced]_September_09_18_2023_20:26:11.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=20_range=[-10.0,10.0]_nb=500_group=[dim20_pred4_prog4_balanced]_July_07_13_2023_16:02:12.json",
    "hte/data/results_compute_arr/Cox_Weibull_1.0_2.0_dim=20_range=[-10.0,10.0]_nb=500_group=[dim20_pred4_prog4_bis_balanced]_July_07_19_2023_10:28:22.json",
    "hte/experiments/results_expe/COMPLEXITY_DIM=[3, 20, 100, 500, 1000]_NB=[500]_REPET=1_October_10_14_2023_08:04:07.csv",
})


def test_the_verdict_tally_is_pinned() -> None:
    claims, verdicts = replay()
    assert len(verdicts.verdicts) == len(claims) == 16
    assert Counter(v.verdict for v in verdicts.verdicts) == _TALLY


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


#: Pinned after the third dev-time run (2026-10-02): 2 of 16 claims matched the paper's
#: Table 1 rates in THIS run; 14 DIVERGED. The run is NOT run-to-run deterministic (three
#: full runs gave different values for every claim — see the README's finding), so the
#: per-run verdicts are run facts; the review refuted all 14 divergences as sampling
#: noise (labels.json: 14× `refuted`), and every DIVERGED carries `review_required`.
_TALLY: Counter = Counter({REPRODUCED: 2, DIVERGED: 14})


def test_a_divergence_would_be_documented_with_its_tension() -> None:
    # The probe found the repo's own committed type-I-error CSVs disagree with the printed
    # Table 1 on several cells. The fresh run at the pinned rev reproduces some paper
    # values (3 REPRODUCED) and contradicts others (13 DIVERGED) — the verdicts decide,
    # and the M4a drift cross-check is recorded in drift.json. On this machine the drift
    # is INCONCLUSIVE by construction (the alternate envs cannot run the pipeline:
    # current resolve breaks lifelines/scipy, the paper-era boundary cannot build qdldl) —
    # the DIVERGEDs stand on the recorded run, review_required, with the limitation
    # documented in the README.
    _, verdicts = replay()
    diverged = [v for v in verdicts.verdicts if v.verdict == DIVERGED]
    for v in diverged:
        assert v.review_required
    drift = json.loads((FIXTURE / "drift.json").read_text(encoding="utf-8"))
    assert drift["inconclusive"] is True
    assert drift["older_environment"]["run_ok"] is False
    assert "inconclusive by construction" in (FIXTURE / "README.md").read_text(
        encoding="utf-8"
    )