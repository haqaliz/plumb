#!/usr/bin/env python3
"""The one dev-time, networked run of the Perrin et al. gate record (panel-run, paper 2).

Fetches the paper's code at the pinned rev and runs it through the real spine:

1. **C2** — `resolve_git` at `76ce145f42fd…` (the last commit before the 2024-01-22 arXiv
   submission), `describe_environment`, and a real `build_environment` through a
   perrin-specific runner.
2. **C3** — `run_and_capture` with an explicit entry point: `python -c <DRIVER>`
   (`tools/perrin_spec.py`), run in a working copy under the run area.
3. **C4** — `verify_claims` over the committed claims and bindings.

**The environment** (probe finding, recorded in the README): the repo is a poetry project;
modern uv no longer reads `[tool.poetry]`/`poetry.lock`, so `uv sync` yields an empty env;
the paper-era boundary (`--exclude-newer 2024-01-23`) cannot build qdldl 0.1.7.post0
(osqp ← scikit-survival) on this Apple-Silicon toolchain. The runner therefore builds at
the earliest buildable boundary — `--exclude-newer 2024-06-18` (qdldl 0.1.7.post3 is the
first arm64 wheel) with Python 3.10.

**The drift cross-check** (PRD M4a): only when a `DIVERGED` appears, the same driver is run
again in a second environment — here a *current* resolve (no boundary), since the paper-era
boundary is unbuildable — and each claim's verdict is compared. A claim whose verdict
differs between the two environments is environment-sensitive; it is listed in `drift.json`
as `UNVERIFIED`, never `DIVERGED`.

Never imported by tests. Network: `git clone` from GitHub and package downloads from PyPI —
authorized by the owner for this record. Run by hand: ``uv run tools/perrin_gate_run.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from perrin_spec import DRIVER, FIXTURE  # noqa: E402

from plumb.extract.claim import Claim  # noqa: E402
from plumb.extract.location import CharSpan  # noqa: E402
from plumb.extract.value import parse_value  # noqa: E402
from plumb.intake import (  # noqa: E402
    EnvBuild,
    build_environment,
    describe_environment,
    resolve_git,
)
from plumb.run import EntryPoint, run_and_capture, serialize_trace  # noqa: E402
from plumb.verify import Completed, load_bindings, serialize_verdicts, verify_claims  # noqa: E402

REPO = "https://github.com/owkin/hte.git"
REV = "76ce145f42fd37a91b389d8c8762de167647f82f"
EXCLUDE_NEWER = "2024-06-18T00:00:00Z"  # earliest boundary buildable on this machine
PYTHON_PIN = "3.10"
TIMEOUT_SECONDS = 12 * 3600  # measured: p=20 alone exceeded 3.6 h wall (probe estimate was optimistic)


def load_claims() -> list[Claim]:
    entries = json.loads((FIXTURE / "claims.json").read_text(encoding="utf-8"))["claims"]
    return [
        Claim(parse_value(e["text"]), None, e["metric"], CharSpan(e["start"], e["end"]), None, None)
        for e in entries
    ]


def freeze(python: Path) -> str:
    out = subprocess.run(
        ["uv", "pip", "freeze", "--python", str(python)], capture_output=True, check=True
    ).stdout.decode()
    version = subprocess.run(
        [str(python), "-c", "import platform; print(platform.python_version())"],
        capture_output=True, check=True,
    ).stdout.decode().strip()
    lines = [f"python=={version}"] + [
        line for line in out.splitlines() if not line.startswith(("hte", "-e "))
    ]
    return "\n".join(lines) + "\n"


def perrin_env_runner(checkout, descriptor, *, boundary: str | None) -> EnvBuild:
    """Build `<checkout>/.venv` at the given `--exclude-newer` boundary (dev-time only).

    `boundary=None` is a current resolve (no boundary) — the flag is omitted.
    """
    venv = checkout.checkout_dir / ".venv"
    subprocess.run(["uv", "venv", "--python", PYTHON_PIN, "--quiet", str(venv)], check=True)
    command = ["uv", "pip", "install", "--quiet", "--python", str(venv / "bin" / "python")]
    if boundary is not None:
        command += ["--exclude-newer", boundary]
    command.append(str(checkout.checkout_dir))
    result = subprocess.run(
        command, capture_output=True, timeout=1800, check=False,
    )
    detail = result.stderr.decode("utf-8", "replace").strip() or result.stdout.decode(
        "utf-8", "replace"
    ).strip() or "installed"
    if result.returncode != 0:
        return EnvBuild(ok=False, policy=descriptor.policy, detail=detail)
    boundary_note = (
        f"uv pip install --exclude-newer {boundary}" if boundary is not None
        else "uv pip install (current resolve, no boundary)"
    )
    return EnvBuild(
        ok=True,
        policy=descriptor.policy,
        detail=f"{boundary_note} (poetry.lock unreadable by modern uv; paper-era "
               f"boundary unbuildable: qdldl) — {detail}",
    )


def run_once(workdir: Path, claims, *, boundary: str | None):
    checkout = resolve_git(REPO, REV, checkout_dir=workdir / "checkout")
    descriptor = describe_environment(checkout)
    build = build_environment(
        checkout, descriptor,
        runner=lambda c, d: perrin_env_runner(c, d, boundary=boundary),
    )
    entry = EntryPoint(argv=("python", "-c", DRIVER), source="explicit")
    trace, capture = run_and_capture(
        checkout, build, entry, run_dir=workdir / "run", timeout_seconds=TIMEOUT_SECONDS
    )
    bindings = load_bindings((FIXTURE / "bindings.json").read_bytes(), [c.id for c in claims])
    verdicts = verify_claims(claims, bindings, Completed(trace, capture))
    python = checkout.checkout_dir / ".venv" / "bin" / "python"
    return checkout, descriptor, trace, capture, verdicts, freeze(python)


def _verdict_key(v) -> str:
    """The claim id of a `Verdict` object or a committed verdicts.json entry."""
    return v["claim_id"] if isinstance(v, dict) else v.claim_id


def _verdict_triple(v) -> tuple:
    """`(verdict, cause, located_text)` of a `Verdict` object or a committed entry."""
    if isinstance(v, dict):
        return (v["verdict"], v["cause"], v["located_text"])
    return (v.verdict, v.cause, v.located_text)


def _drift_report(
    root: Path, claims, metrics, verdicts_a, trace_a, run_id_a, env_a_text,
) -> dict:
    """The M4a drift cross-check: the recorded env's verdicts vs a second buildable env.

    The second env is the **current resolve** (no boundary). On this repo the current
    resolve cannot run the pipeline at all (lifelines 0.27.7 imports `scipy.integrate.trapz`,
    removed in scipy>=1.14 — the current resolve), and the paper-era boundary cannot build
    qdldl on this machine — so the cross-check is **inconclusive by construction** unless a
    second buildable, runnable env exists. The report records the truth of what happened;
    it never fabricates a comparison.
    """
    try:
        _, _, trace_b, _, verdicts_b, env_b = run_once(root / "b", claims, boundary=None)
    except Exception as exc:  # EnvBuildFailed etc.: the second env does not exist
        return {
            "older_environment": {
                "exclude_newer": None,
                "note": f"current resolve could not be built or resolved ({type(exc).__name__}); "
                        "paper-era boundary (2024-01-23) cannot build qdldl 0.1.7.post0 on "
                        "this machine",
                "run_ok": False,
            },
            "same_outputs": None,
            "verdicts_changed": None,
            "inconclusive": True,
        }
    if trace_b.failure is not None:
        return {
            "older_environment": {
                "exclude_newer": None,
                "note": f"current resolve built but the pipeline did not run "
                        f"({trace_b.failure.cause}); paper-era boundary (2024-01-23) cannot "
                        "build qdldl 0.1.7.post0 on this machine",
                "run_ok": False,
            },
            "same_outputs": None,
            "verdicts_changed": None,
            "inconclusive": True,
        }
    a = {_verdict_key(v): _verdict_triple(v) for v in verdicts_a}
    b = {_verdict_key(v): _verdict_triple(v) for v in verdicts_b.verdicts}
    changed = [
        {"claim_id": cid, "metric": metrics[cid],
         "recorded": list(a[cid]),
         "other": list(b[cid])}
        for cid in sorted(a)
        if a[cid] != b[cid]
    ]
    return {
        "older_environment": {
            "exclude_newer": None,
            "note": "current resolve (no boundary): the paper-era boundary (2024-01-23) "
                    "cannot build qdldl 0.1.7.post0 on this machine",
            "run_ok": True,
            "freeze": env_b.splitlines(),
        },
        "same_outputs": trace_b.run_id == run_id_a,
        "verdicts_changed": changed,
        "inconclusive": False,
    }


def main() -> int:
    claims = load_claims()
    metrics = {c.id: c.metric for c in claims}
    with tempfile.TemporaryDirectory(prefix="plumb-gate-") as tmp:
        root = Path(tmp)
        if "--drift-only" in sys.argv:
            committed = json.loads((FIXTURE / "verdicts.json").read_text(encoding="utf-8"))
            drift = _drift_report(
                root, claims, metrics,
                verdicts_a=committed["verdicts"], trace_a=None,
                run_id_a=committed["run_id"], env_a_text=None,
            )
            (FIXTURE / "drift.json").write_text(
                json.dumps(drift, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(drift, indent=1))
            return 0

        checkout, descriptor, trace, capture, verdicts, env = run_once(
            root / "a", claims, boundary=EXCLUDE_NEWER
        )
        if trace.failure is not None:
            print(f"run failed: {trace.failure.cause}: {trace.failure.detail}", file=sys.stderr)
            print(capture.read(next(a for a in capture.artifacts if a.kind == "stderr")).decode(
                "utf-8", "replace")[-4000:], file=sys.stderr)
            return 1

        (FIXTURE / "trace.json").write_bytes(serialize_trace(trace))
        objects = FIXTURE / "objects"
        shutil.rmtree(objects, ignore_errors=True)
        objects.mkdir()
        for artifact in capture.locatable:
            (objects / artifact.sha256).write_bytes(capture.read(artifact))
        (FIXTURE / "verdicts.json").write_bytes(serialize_verdicts(verdicts))
        header = (
            f"# resolved by uv pip install --exclude-newer {EXCLUDE_NEWER} "
            f"(policy {descriptor.policy!r}: {descriptor.policy_detail}) on the pinned "
            f"checkout {REV}; poetry.lock is unreadable by modern uv and the paper-era "
            f"boundary (2024-01-23) cannot build qdldl on this toolchain; descriptor "
            f"python pin {descriptor.python_pin!r} ({descriptor.python_pin_source}); "
            f"interpreter built {PYTHON_PIN}; tools: "
            + ", ".join(f"{k}={v}" for k, v in descriptor.tool_versions) + "\n"
        )
        (FIXTURE / "environment.txt").write_text(header + env, encoding="utf-8")

        diverged = [v for v in verdicts.verdicts if v.verdict == "DIVERGED"]
        if diverged:
            print(f"{len(diverged)} DIVERGED claims — running the drift cross-check "
                  f"(current resolve vs {EXCLUDE_NEWER})", file=sys.stderr)
            drift = _drift_report(
                root / "b", claims, metrics,
                verdicts_a=verdicts.verdicts, trace_a=trace,
                run_id_a=trace.run_id, env_a_text=env,
            )
            (FIXTURE / "drift.json").write_text(
                json.dumps(drift, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            (FIXTURE / "drift.json").unlink(missing_ok=True)

    coverage = verdicts.coverage
    print(json.dumps(coverage, indent=1))
    print(f"run_id {trace.run_id}")
    for v in verdicts.verdicts:
        if v.verdict != "REPRODUCED":
            print(v.verdict, v.cause, metrics[v.claim_id], v.reported_text, "->", v.located_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())