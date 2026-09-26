#!/usr/bin/env python3
"""The one dev-time, networked run of the AgroDesign gate record (gate-paper G4, PRD M6).

Fetches the paper's code at the pinned tag and runs it through the real spine:

1. **C2** — `resolve_git` at `v1.0.1`, `describe_environment`, and a real
   `build_environment` through `uv_sync_runner` (the repo has no lockfile and no requirements
   file, so the recorded policy is "best-effort": `uv sync` resolves the declared ranges now).
2. **C3** — `run_and_capture` with an explicit entry point: `python -c <DRIVER>`, the paper's
   appendix workflow (`tools/agrodesign_spec.py`), run in a working copy under the run area.
3. **C4** — `verify_claims` over the committed claims and bindings.

It writes into `fixtures/gate/agrodesign/`: `trace.json`, `objects/` (the *locatable* captured
outputs only — stderr is diagnostic and may carry local paths), `verdicts.json`,
`environment.txt`, and `drift.json`.

**The drift cross-check** (PRD M4a): the same driver is run a second time, through the same
spine, in an environment resolved with `uv pip install --exclude-newer 2026-02-12` — the newest
releases available when the pinned code was written — and each claim's verdict is compared.
A claim whose verdict differs between the two environments is environment-sensitive; it is
listed in `drift.json` and the README says so.

Never imported by tests. Network: `git clone` from GitHub and package downloads from PyPI —
authorized by the owner for this record. Run by hand: ``uv run tools/gate_run.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agrodesign_spec import DRIVER, FIXTURE  # noqa: E402

from plumb.extract.claim import Claim  # noqa: E402
from plumb.extract.location import CharSpan  # noqa: E402
from plumb.extract.value import parse_value  # noqa: E402
from plumb.intake import (  # noqa: E402
    EnvBuild,
    build_environment,
    describe_environment,
    resolve_git,
    uv_sync_runner,
)
from plumb.run import EntryPoint, run_and_capture, serialize_trace  # noqa: E402
from plumb.verify import Completed, load_bindings, serialize_verdicts, verify_claims  # noqa: E402

REPO = "https://github.com/DeepStatistix/AgroDesign.git"
REV = "v1.0.1"
EXCLUDE_NEWER = "2026-02-12T00:00:00Z"
TIMEOUT_SECONDS = 900


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
        line for line in out.splitlines() if not line.startswith(("agrodesign", "-e "))
    ]
    return "\n".join(lines) + "\n"


def run_once(workdir: Path, claims, *, older: bool):
    checkout = resolve_git(REPO, REV, checkout_dir=workdir / "checkout")
    if older:
        venv = checkout.checkout_dir / ".venv"
        subprocess.run(["uv", "venv", "--quiet", str(venv)], check=True)
        subprocess.run(
            ["uv", "pip", "install", "--quiet", "--python", str(venv / "bin" / "python"),
             "--exclude-newer", EXCLUDE_NEWER, str(checkout.checkout_dir)],
            check=True,
        )
        build = EnvBuild(ok=True, policy="best-effort", detail=f"exclude-newer {EXCLUDE_NEWER}")
        descriptor = None
    else:
        descriptor = describe_environment(checkout)
        build = build_environment(checkout, descriptor, runner=uv_sync_runner)
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
        checkout, descriptor, trace, capture, verdicts, env = run_once(root / "a", claims, older=False)
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
            f"# resolved by uv sync (policy {descriptor.policy!r}: {descriptor.policy_detail}) "
            f"on the pinned checkout {REV}; python pin {descriptor.python_pin!r} "
            f"({descriptor.python_pin_source}); tools: "
            + ", ".join(f"{k}={v}" for k, v in descriptor.tool_versions) + "\n"
        )
        (FIXTURE / "environment.txt").write_text(header + env, encoding="utf-8")

        _, _, trace_b, _, verdicts_b, env_b = run_once(root / "b", claims, older=True)
        a = {v.claim_id: v for v in verdicts.verdicts}
        b = {v.claim_id: v for v in verdicts_b.verdicts}
        changed = [
            {"claim_id": cid, "metric": metrics[cid],
             "current": [a[cid].verdict, a[cid].cause, a[cid].located_text],
             "older": [b[cid].verdict, b[cid].cause, b[cid].located_text]}
            for cid in sorted(a)
            if (a[cid].verdict, a[cid].cause) != (b[cid].verdict, b[cid].cause)
        ]
        drift = {
            "older_environment": {"exclude_newer": EXCLUDE_NEWER,
                                  "run_ok": trace_b.failure is None,
                                  "freeze": env_b.splitlines()},
            "same_outputs": trace_b.run_id == trace.run_id,
            "verdicts_changed": changed,
        }
        (FIXTURE / "drift.json").write_text(
            json.dumps(drift, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )

    coverage = verdicts.coverage
    print(json.dumps(coverage, indent=1))
    print(f"run_id {trace.run_id}")
    print(f"older env: same outputs = {drift['same_outputs']}, verdict changes = {len(changed)}")
    for v in verdicts.verdicts:
        if v.verdict != "REPRODUCED":
            print(v.verdict, v.cause, metrics[v.claim_id], v.reported_text, "->", v.located_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
