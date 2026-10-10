#!/usr/bin/env python3
"""The one dev-time, networked run of the rcai gate record (notebook-paper, PRD P4).

Fetches the paper's code at the pinned rev and runs it through the real spine, with the
**notebook fallback entry rule** (the spine's own rule — never a guess):

1. **C2** — `resolve_git` at the pinned rev (d50b33ee, the probe commit), a real
   `build_environment` through an rcai-specific runner that installs the notebook's declared
   deps (README versions) plus `jupyter`/`nbconvert` into `<checkout>/.venv`.
2. **C3** — `resolve_entrypoint` (no `[project.scripts]`, no root `main.py`, one root
   `*.ipynb` → the notebook rule) then `run_and_capture`: `jupyter nbconvert --execute
   --inplace` in a working copy under the run area, freshness-guarded.
3. **C4** — `verify_claims` over the committed claims and bindings (notebook_cell locators,
   HTML table-cell addressing per N1).

It writes into `fixtures/gate/rcai/`: `trace.json`, `objects/` (locatable only), and
`verdicts.json` (re-derived, cross-checked byte-for-byte), plus `drift.json` with the
run-to-run determinism record (a second full run in a fresh working copy/venv — the code has
zero RNG, so verdicts must be identical) and the env note.

**Determinism / drift note** (PRD G5, M4a precedent): the cross-check run is the same resolve
(a second buildable env does not exist — the code is ~6 weeks old, no lockfile, the only
boundary is a fresh resolve); `drift.json` records the truth of that, never a fabricated
comparison. A `DIVERGED` in the recorded run is not environment-sensitive by construction
(zero RNG, byte-identical second run) — unless the second run disagrees, which would itself
be recorded.

Never imported by tests. Network: `git clone` from GitHub and package downloads from PyPI —
authorized by the owner for this record. Run by hand: ``uv run tools/rcai_run.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rcai_spec import FIXTURE  # noqa: E402

from plumb.extract.claim import Claim  # noqa: E402
from plumb.extract.location import CharSpan  # noqa: E402
from plumb.extract.value import parse_value  # noqa: E402
from plumb.intake import (  # noqa: E402
    EnvBuild,
    build_environment,
    describe_environment,
    resolve_git,
    scan_manifests,
)
from plumb.run import EntryPoint, resolve_entrypoint, run_and_capture, serialize_trace  # noqa: E402
from plumb.verify import Completed, load_bindings, serialize_verdicts, verify_claims  # noqa: E402

REPO = "https://github.com/burtsev/recursive-criticality-ai.git"
REV = "d50b33eeced3a036ef31cd2de534016f50f61c3c"
PYTHON_PIN = "3.13"
TIMEOUT_SECONDS = 1500  # dev budget ≤ 20 min (probe estimate ~5)
DEPS = [
    "numpy", "pandas", "scipy", "matplotlib", "networkx", "tqdm", "ipython",
    "numba", "jupyter", "nbconvert",
]


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
        line for line in out.splitlines() if not line.startswith(
            ("recursive-criticality-ai", "-e ")
        )
    ]
    return "\n".join(lines) + "\n"


def rcai_env_runner(checkout, descriptor) -> EnvBuild:
    """Build `<checkout>/.venv` with the notebook's declared deps (dev-time only)."""
    venv = checkout.checkout_dir / ".venv"
    subprocess.run(["uv", "venv", "--python", PYTHON_PIN, "--quiet", str(venv)], check=True)
    result = subprocess.run(
        ["uv", "pip", "install", "--quiet", "--python", str(venv / "bin" / "python")] + DEPS,
        capture_output=True, timeout=1800, check=False,
    )
    detail = result.stderr.decode("utf-8", "replace").strip() or result.stdout.decode(
        "utf-8", "replace"
    ).strip() or "installed"
    if result.returncode != 0:
        return EnvBuild(ok=False, policy=descriptor.policy, detail=detail)
    return EnvBuild(
        ok=True,
        policy=descriptor.policy,
        detail=(
            f"uv pip install {' '.join(DEPS)} (no lockfile; README-declared versions; "
            f"fresh resolve is the only env — no era boundary exists) — {detail}"
        ),
    )


def run_once(workdir: Path, claims):
    checkout = resolve_git(REPO, REV, checkout_dir=workdir / "checkout")
    descriptor = describe_environment(checkout)
    manifests = scan_manifests(checkout)
    entry: EntryPoint = resolve_entrypoint(checkout, manifests)
    build = build_environment(
        checkout, descriptor, runner=lambda c, d: rcai_env_runner(c, d)
    )
    trace, capture = run_and_capture(
        checkout, build, entry, run_dir=workdir / "run", timeout_seconds=TIMEOUT_SECONDS
    )
    bindings = load_bindings((FIXTURE / "bindings.json").read_bytes(), [c.id for c in claims])
    verdicts = verify_claims(claims, bindings, Completed(trace, capture))
    python = checkout.checkout_dir / ".venv" / "bin" / "python"
    return checkout, descriptor, entry, trace, capture, verdicts, freeze(python)


def main() -> int:
    claims = load_claims()
    metrics = {c.id: c.metric for c in claims}
    with tempfile.TemporaryDirectory(prefix="plumb-rcai-") as tmp:
        root = Path(tmp)
        checkout, descriptor, entry, trace, capture, verdicts, env = run_once(root / "a", claims)
        if trace.failure is not None:
            print(f"run failed: {trace.failure.cause}: {trace.failure.detail}", file=sys.stderr)
            print(capture.read(next(a for a in capture.artifacts if a.kind == "stderr")).decode(
                "utf-8", "replace")[-4000:], file=sys.stderr)
            return 1
        print(f"entry_point {entry.argv[0]} {' '.join(entry.argv[1:])}")
        print(f"run_id {trace.run_id}")

        (FIXTURE / "trace.json").write_bytes(serialize_trace(trace))
        objects = FIXTURE / "objects"
        shutil.rmtree(objects, ignore_errors=True)
        objects.mkdir()
        for artifact in capture.locatable:
            (objects / artifact.sha256).write_bytes(capture.read(artifact))
        committed_verdicts = serialize_verdicts(verdicts)
        (FIXTURE / "verdicts.json").write_bytes(committed_verdicts)
        header = (
            f"# resolved by uv pip install (policy {descriptor.policy!r}: "
            f"{descriptor.policy_detail}) on the pinned checkout {REV}; python "
            f"{PYTHON_PIN}; tools: "
            + ", ".join(f"{k}={v}" for k, v in descriptor.tool_versions) + "\n"
        )
        env_path = FIXTURE / "environment.txt"
        env_path.write_text(header + env, encoding="utf-8")

        # run-to-run determinism: a second full run in a fresh working copy + venv (zero RNG).
        _, _, _, trace_b, _, verdicts_b, env_b = run_once(root / "b", claims)
        run_b_ok = trace_b.failure is None
        a = {v.claim_id: v for v in verdicts.verdicts}
        b = {v.claim_id: v for v in verdicts_b.verdicts}
        changed = [
            {"claim_id": cid, "metric": metrics[cid],
             "run_a": [a[cid].verdict, a[cid].cause, a[cid].located_text],
             "run_b": [b[cid].verdict, b[cid].cause, b[cid].located_text]}
            for cid in sorted(a)
            if (a[cid].verdict, a[cid].cause) != (b[cid].verdict, b[cid].cause)
        ]
        drift = {
            "determinism": {
                "second_run_ok": run_b_ok,
                "same_run_id": trace_b.run_id == trace.run_id,
                "verdicts_changed": changed,
                "freeze_b": env_b.splitlines(),
            },
            "environment": {
                "note": "fresh resolve only — the code is ~6 weeks old, no lockfile, no era "
                        "boundary exists on this machine; no second buildable env for an "
                        "M4a cross-check (recorded, not assumed away)",
            },
        }
        (FIXTURE / "drift.json").write_text(
            json.dumps(drift, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        # confirm verdicts.json is byte-identical to the re-derived cross-check. Exit
        # code 1 with an UNVERIFIED claim is the CLI's honest contract (the KAA claim is
        # NO_BINDING) — identity is proven by the bytes, not the exit code.
        replay = subprocess.run(
            [sys.executable, "-c",
             "import sys; from plumb.cli import main as m; sys.exit(m(['verify', '--json', "
             "'--from-record', %r]))" % str(FIXTURE)],
            capture_output=True, text=True,
        )
        if (FIXTURE / "verdicts.json").read_bytes() != replay.stdout.encode("utf-8"):
            print("replay stdout differs from the committed verdicts.json", file=sys.stderr)
            return 1
        if replay.returncode not in (0, 1):
            print(f"replay failed: {replay.stderr[-2000:]}", file=sys.stderr)
            return 1

    coverage = verdicts.coverage
    print(json.dumps(coverage, indent=1))
    print(f"determinism: second run ok={run_b_ok}, same run_id={drift['determinism']['same_run_id']}, "
          f"verdict changes={len(changed)}")
    for v in verdicts.verdicts:
        if v.verdict != "REPRODUCED":
            print(v.verdict, v.cause, metrics[v.claim_id], v.reported_text, "->", v.located_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())