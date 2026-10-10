"""The false-`DIVERGED` guard (M8, risk R2): no harness failure is ever a finding.

For every way a run can fail — nothing ran, it exited non-zero, it timed out, it
wrote nothing, the bound output predates it — the claim is bound to a value that
**would** diverge (the paper says `0.87`, the output holds `0.95`). Every record
must be `UNVERIFIED` with that failure's own cause. A `DIVERGED` here would be the
reputational poison `docs/ROADMAP.md` R2 describes: a harness fault published as a
paper error.

**The guard is mutation-checked.** A guard that passes whatever the code does
proves nothing, so the suite also runs it against deliberately broken code and
asserts it *fails*:

- with the run-level precedence removed (`_run_level_cause` → `None`), a failed
  run's captured output is read and diverges;
- with C4's stale check removed (`locate._stale_target` → `False`) and a stale
  output leaked into the capture as if C3's freshness guard had been loosened,
  the committed value is read and diverges;
- with a cell's `#cell-<i>` → notebook file resolution removed
  (`locate._cell_file` → identity), a stale notebook's leaked cell artifact is
  read and diverges;
- with the D13 reach rule removed (`compare._within_reach` → `False`), a band
  claim whose coarse artifact sits just outside the boundary is no longer
  rescued and becomes `DIVERGED`.

The leaked case is also part of the guard itself: a relpath the capture records
as stale is refused even if an artifact of the same path is present, so C4's
refusal does not depend on C3's alone.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path

import pytest

import plumb.verify as verify
from plumb.intake.causes import EnvBuildFailed
from plumb.run.capture import Artifact
from plumb.run.causes import EntryPointAmbiguous, EntryPointMissing
from plumb.run.trace import build_trace
from plumb.verify import DIVERGED, UNVERIFIED, Completed, NoRun, load_bindings
from plumb.verify import causes
from plumb.verify.bindings import Binding
from verify_helpers import (
    OLD,
    bindings_json,
    claim,
    notebook_bytes,
    prints,
    run_full,
    writes,
    writes_notebook,
)

locate_module = importlib.import_module("plumb.verify.locate")
compare_module = importlib.import_module("plumb.verify.compare")

PAPER = claim("0.87", "AUC")
DIVERGING = '{"auc": 0.95}'
BINDING = load_bindings(
    bindings_json((PAPER, "results.json", {"kind": "json_pointer", "pointer": "/auc"})),
    [PAPER.id],
)

PM = claim("0.850 ± 0.030")
NEAR_BOUNDARY = '{"auc": 0.9}'
PM_BINDING = load_bindings(
    bindings_json((PM, "results.json", {"kind": "json_pointer", "pointer": "/auc"})),
    [PM.id],
)


def _completed(tmp_path: Path, program: str, **kw) -> Completed:
    _, _, capture, trace = run_full(tmp_path, program, **kw)
    return Completed(trace, capture)


def _leaked_stale(tmp_path: Path) -> Completed:
    """A committed, back-dated output that the capture *also* lists as an artifact."""
    checkout, result, capture, _ = run_full(
        tmp_path, prints("done\n"), files={"results.json": DIVERGING.encode()}
    )
    (stale,) = capture.stale
    data = (checkout.checkout_dir / stale.relpath).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    (capture.store / digest).write_bytes(data)
    leaked = Artifact("json", stale.relpath, digest, len(data), stale.mtime_ns)
    capture = replace(
        capture, artifacts=tuple(sorted((*capture.artifacts, leaked),
                                        key=lambda a: (a.kind, a.relpath)))
    )
    return Completed(build_trace(checkout, result, capture), capture)


NOTEBOOK_CELLS = [
    {
        "cell_type": "code",
        "execution_count": 1,
        "metadata": {},
        "outputs": [{"output_type": "stream", "name": "stdout", "text": ["0.95\n"]}],
        "source": ["print(0.95)"],
    },
]

NOTEBOOK_BINDING = load_bindings(
    bindings_json((
        PAPER,
        "analysis.ipynb#cell-0",
        {"kind": "notebook_cell", "pointer": "/0/text/0"},
    )),
    [PAPER.id],
)


def _leaked_stale_cell(tmp_path: Path) -> Completed:
    """A committed, back-dated notebook the capture *also* lists as cell artifacts."""
    checkout, result, capture, _ = run_full(
        tmp_path, prints("done\n"), files={"analysis.ipynb": notebook_bytes(NOTEBOOK_CELLS)}
    )
    (stale,) = capture.stale
    canonical = (
        json.dumps(
            NOTEBOOK_CELLS[0]["outputs"], sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    (capture.store / digest).write_bytes(canonical)
    leaked = Artifact(
        "notebook_cell", "analysis.ipynb#cell-0", digest, len(canonical), stale.mtime_ns
    )
    capture = replace(
        capture, artifacts=tuple(sorted((*capture.artifacts, leaked),
                                        key=lambda a: (a.kind, a.relpath)))
    )
    return Completed(build_trace(checkout, result, capture), capture)


def _no_output_cell(tmp_path: Path) -> Completed:
    """A run whose notebook cell produced nothing to read."""
    cells = [{
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": ["print(0.95)"],
    }]
    return _completed(tmp_path, writes_notebook("analysis.ipynb", cells))


#: (name, expected cause, binding, builder of the run)
SCENARIOS: list[tuple[str, str, Mapping[str, Binding],
                      Callable[[Path], Completed | NoRun]]] = [
    ("entrypoint missing", causes.ENTRYPOINT_MISSING, BINDING,
     lambda _: NoRun.from_exception(EntryPointMissing("none"))),
    ("entrypoint ambiguous", causes.ENTRYPOINT_AMBIGUOUS, BINDING,
     lambda _: NoRun.from_exception(EntryPointAmbiguous("two"))),
    ("env build failed", causes.ENV_BUILD_FAILED, BINDING,
     lambda _: NoRun.from_exception(EnvBuildFailed("uv sync failed"))),
    ("won't run", causes.WONT_RUN, BINDING,
     lambda t: _completed(t, writes("results.json", DIVERGING) + "raise SystemExit(3)\n")),
    ("timeout", causes.TIMEOUT, BINDING,
     lambda t: _completed(
         t, writes("results.json", DIVERGING) + "import time\ntime.sleep(30)\n",
         timeout_seconds=1,
     )),
    ("no artifact", causes.NO_ARTIFACT, BINDING, lambda t: _completed(t, "pass\n")),
    ("stale artifact", causes.STALE_ARTIFACT, BINDING,
     lambda t: _completed(t, prints("done\n"), files={"results.json": DIVERGING.encode()})),
    ("stale artifact, leaked into the capture", causes.STALE_ARTIFACT, BINDING, _leaked_stale),
    ("stale notebook cell, leaked into the capture", causes.STALE_ARTIFACT,
     NOTEBOOK_BINDING, _leaked_stale_cell),
    ("no-output notebook cell", causes.NO_BINDING, NOTEBOOK_BINDING, _no_output_cell),
]


def assert_guard(tmp_path: Path) -> set[str]:
    """Every scenario is UNVERIFIED with its own cause; returns the causes seen.

    All scenarios run before anything is asserted, so one failure message names
    every scenario that broke — a mutation test can then match the specific
    breakage (a DIVERGED) rather than whichever scenario happened to fail first.
    """
    seen, broken = set(), []
    for index, (name, expected, binding, build) in enumerate(SCENARIOS):
        run = build(tmp_path / f"s{index}")
        (verdict,) = verify.verify_claims([PAPER], binding, run).verdicts
        if verdict.verdict == DIVERGED:
            broken.append(f"{name}: a harness failure became DIVERGED")
        elif (verdict.verdict, verdict.cause) != (UNVERIFIED, expected):
            broken.append(f"{name}: expected UNVERIFIED {expected}, got {verdict.verdict} "
                          f"{verdict.cause}")
        seen.add(verdict.cause)
    assert not broken, "; ".join(broken)
    return seen


def test_no_run_failure_is_ever_diverged(tmp_path: Path) -> None:
    assert assert_guard(tmp_path) == {cause for _, cause, _, _ in SCENARIOS}


def assert_d13(tmp_path: Path) -> str:
    """A coarse artifact just outside a band's boundary is never DIVERGED (D13).

    All checks run before anything is asserted, so a mutation failure names the
    DIVERGED rather than whichever check happened to run first.
    """
    run = _completed(tmp_path, writes("results.json", NEAR_BOUNDARY))
    (verdict,) = verify.verify_claims([PM], PM_BINDING, run).verdicts
    assert verdict.verdict != DIVERGED, "a coarse near-boundary artifact became DIVERGED"
    assert (verdict.verdict, verdict.cause) == (
        UNVERIFIED, causes.ARTIFACT_PRECISION_COARSER,
    )
    return verdict.cause


def test_a_coarse_near_boundary_band_value_is_never_diverged(tmp_path: Path) -> None:
    assert assert_d13(tmp_path) == causes.ARTIFACT_PRECISION_COARSER


def test_the_same_binding_does_diverge_on_a_healthy_run(tmp_path: Path) -> None:
    # The control: the guard's binding is not inert — against a clean run it bites.
    run = _completed(tmp_path, writes("results.json", DIVERGING))
    (verdict,) = verify.verify_claims([PAPER], BINDING, run).verdicts
    assert verdict.verdict == DIVERGED


def test_the_notebook_binding_does_diverge_on_a_healthy_run(tmp_path: Path) -> None:
    # The control: the stale-cell scenario's value really diverges when the
    # notebook is fresh — the guard refuses it for staleness, not for nothing.
    run = _completed(tmp_path, writes_notebook("analysis.ipynb", NOTEBOOK_CELLS))
    (verdict,) = verify.verify_claims([PAPER], NOTEBOOK_BINDING, run).verdicts
    assert verdict.verdict == DIVERGED


class TestMutations:
    def test_removing_the_run_level_precedence_breaks_the_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(verify, "_run_level_cause", lambda trace: None)
        with pytest.raises(AssertionError, match="became DIVERGED"):
            assert_guard(tmp_path)

    def test_removing_the_stale_check_breaks_the_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(locate_module, "_stale_target", lambda binding, capture: False)
        with pytest.raises(AssertionError, match="became DIVERGED"):
            assert_guard(tmp_path)

    def test_not_resolving_a_cell_to_its_notebook_file_breaks_the_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(locate_module, "_cell_file", lambda artifact: artifact)
        with pytest.raises(AssertionError, match="became DIVERGED"):
            assert_guard(tmp_path)

    def test_removing_the_d13_reach_check_breaks_the_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(compare_module, "_within_reach", lambda boundary, re, a: False)
        with pytest.raises(AssertionError, match="became DIVERGED"):
            assert_d13(tmp_path)


def test_the_leaked_output_really_is_back_dated(tmp_path: Path) -> None:
    run = _leaked_stale(tmp_path)
    (stale,) = run.capture.stale
    assert stale.mtime_ns == OLD * 1_000_000_000
    assert any(a.relpath == stale.relpath for a in run.capture.locatable)
