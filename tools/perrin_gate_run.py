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
TIMEOUT_SECONDS = 4 * 3600  # p=20 (~2.1 h) + p=100 (~47 min) at 1000 repetitions


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


def perrin_env_runner(checkout, descriptor, *, boundary: str) -> EnvBuild:
    """Build `<checkout>/.venv` at the given `--exclude-newer` boundary (dev-time only)."""
    venv = checkout.checkout_dir / ".venv"
    subprocess.run(["uv", "venv", "--python", PYTHON_PIN, "--quiet", str(venv)], check=True)
    result = subprocess.run(
        ["uv", "pip", "install", "--quiet", "--python", str(venv / "bin" / "python"),
         "--exclude-newer", boundary, str(checkout.checkout_dir)],
        capture_output=True,
        timeout=1800,
        check=False,
    )
    detail = result.stderr.decode("utf-8", "replace").strip() or result.stdout.decode(
        "utf-8", "replace"
    ).strip() or "installed"
    if result.returncode != 0:
        return EnvBuild(ok=False, policy=descriptor.policy, detail=detail)
    return EnvBuild(
        ok=True,
        policy=descriptor.policy,
        detail=f"uv pip install --exclude-newer {boundary} (poetry.lock unreadable by "
               f"modern uv; paper-era boundary unbuildable: qdldl) — {detail}",
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


def main() -> int:
    claims = load_claims()
    metrics = {c.id: c.metric for c in claims}
    with tempfile.TemporaryDirectory(prefix="plumb-gate-") as tmp:
        root = Path(tmp)
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
            f"boundary (2024-01-23) cannot build qdldl on this toolchain; python pin "
            f"{descriptor.python_pin!r} ({descriptor.python_pin_source}); tools: "
            + ", ".join(f"{k}={v}" for k, v in descriptor.tool_versions) + "\n"
        )
        (FIXTURE / "environment.txt").write_text(header + env, encoding="utf-8")

        diverged = [v for v in verdicts.verdicts if v.verdict == "DIVERGED"]
        if diverged:
            print(f"{len(diverged)} DIVERGED claims — running the drift cross-check "
                  f"(current resolve vs {EXCLUDE_NEWER})", file=sys.stderr)
            _, _, trace_b, _, verdicts_b, env_b = run_once(
                root / "b", claims, boundary=None
            )
            a = {v.claim_id: v for v in verdicts.verdicts}
            b = {v.claim_id: v for v in verdicts_b.verdicts}
            changed = [
                {"claim_id": cid, "metric": metrics[cid],
                 "current": [a[cid].verdict, a[cid].cause, a[cid].located_text],
                 "other": [b[cid].verdict, b[cid].cause, b[cid].located_text]}
                for cid in sorted(a)
                if (a[cid].verdict, a[cid].cause) != (b[cid].verdict, b[cid].cause)
            ]
            drift = {
                "older_environment": {"exclude_newer": None,
                                      "note": "current resolve (no boundary): the "
                                              "paper-era boundary (2024-01-23) cannot "
                                              "build qdldl 0.1.7.post0 on this machine",
                                      "run_ok": trace_b.failure is None,
                                      "freeze": env_b.splitlines()},
                "same_outputs": trace_b.run_id == trace.run_id,
                "verdicts_changed": changed,
            }
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