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
  the committed value is read and diverges.

The leaked case is also part of the guard itself: a relpath the capture records
as stale is refused even if an artifact of the same path is present, so C4's
refusal does not depend on C3's alone.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import hashlib
import importlib
from pathlib import Path

import pytest

import plumb.verify as verify
from plumb.intake.causes import EnvBuildFailed
from plumb.run.capture import Artifact
from plumb.run.causes import EntryPointAmbiguous, EntryPointMissing
from plumb.run.trace import build_trace
from plumb.verify import DIVERGED, UNVERIFIED, Completed, NoRun, load_bindings
from plumb.verify import causes
from verify_helpers import OLD, bindings_json, claim, prints, run_full, writes

locate_module = importlib.import_module("plumb.verify.locate")

PAPER = claim("0.87", "AUC")
DIVERGING = '{"auc": 0.95}'
BINDING = load_bindings(
    bindings_json((PAPER, "results.json", {"kind": "json_pointer", "pointer": "/auc"})),
    [PAPER.id],
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


#: (name, expected cause, builder of the run)
SCENARIOS: list[tuple[str, str, Callable[[Path], Completed | NoRun]]] = [
    ("entrypoint missing", causes.ENTRYPOINT_MISSING,
     lambda _: NoRun.from_exception(EntryPointMissing("none"))),
    ("entrypoint ambiguous", causes.ENTRYPOINT_AMBIGUOUS,
     lambda _: NoRun.from_exception(EntryPointAmbiguous("two"))),
    ("env build failed", causes.ENV_BUILD_FAILED,
     lambda _: NoRun.from_exception(EnvBuildFailed("uv sync failed"))),
    ("won't run", causes.WONT_RUN,
     lambda t: _completed(t, writes("results.json", DIVERGING) + "raise SystemExit(3)\n")),
    ("timeout", causes.TIMEOUT,
     lambda t: _completed(
         t, writes("results.json", DIVERGING) + "import time\ntime.sleep(30)\n",
         timeout_seconds=1,
     )),
    ("no artifact", causes.NO_ARTIFACT, lambda t: _completed(t, "pass\n")),
    ("stale artifact", causes.STALE_ARTIFACT,
     lambda t: _completed(t, prints("done\n"), files={"results.json": DIVERGING.encode()})),
    ("stale artifact, leaked into the capture", causes.STALE_ARTIFACT, _leaked_stale),
]


def assert_guard(tmp_path: Path) -> set[str]:
    """Every scenario is UNVERIFIED with its own cause; returns the causes seen.

    All scenarios run before anything is asserted, so one failure message names
    every scenario that broke — a mutation test can then match the specific
    breakage (a DIVERGED) rather than whichever scenario happened to fail first.
    """
    seen, broken = set(), []
    for index, (name, expected, build) in enumerate(SCENARIOS):
        run = build(tmp_path / f"s{index}")
        (verdict,) = verify.verify_claims([PAPER], BINDING, run).verdicts
        if verdict.verdict == DIVERGED:
            broken.append(f"{name}: a harness failure became DIVERGED")
        elif (verdict.verdict, verdict.cause) != (UNVERIFIED, expected):
            broken.append(f"{name}: expected UNVERIFIED {expected}, got {verdict.verdict} "
                          f"{verdict.cause}")
        seen.add(verdict.cause)
    assert not broken, "; ".join(broken)
    return seen


def test_no_run_failure_is_ever_diverged(tmp_path: Path) -> None:
    assert assert_guard(tmp_path) == {cause for _, cause, _ in SCENARIOS}


def test_the_same_binding_does_diverge_on_a_healthy_run(tmp_path: Path) -> None:
    # The control: the guard's binding is not inert — against a clean run it bites.
    run = _completed(tmp_path, writes("results.json", DIVERGING))
    (verdict,) = verify.verify_claims([PAPER], BINDING, run).verdicts
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


def test_the_leaked_output_really_is_back_dated(tmp_path: Path) -> None:
    run = _leaked_stale(tmp_path)
    (stale,) = run.capture.stale
    assert stale.mtime_ns == OLD * 1_000_000_000
    assert any(a.relpath == stale.relpath for a in run.capture.locatable)
