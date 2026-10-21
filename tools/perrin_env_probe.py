#!/usr/bin/env python3
"""The Perrin environment probe (dev-time, networked; never imported by tests).

Answers the one question the 2026-10-17 poetry policy left open: does the **generic** C2 path —
`describe_environment` → `uv_sync_runner` — now build `owkin/hte` at the pinned rev, instead of
routing a poetry project into an empty `uv sync`? It does not run the paper (the measured run is
12 h) and it does not pick a `--exclude-newer` boundary (that stays in
`tools/perrin_gate_run.py`, and the paper-era boundary is unbuildable: qdldl on arm64).

Usage: ``uv run tools/perrin_env_probe.py`` — prints the descriptor, the build outcome and the
frozen package count, then exits 0 (built) or 1 (failed).
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile

from plumb.intake import build_environment, describe_environment, resolve_git
from plumb.intake.env import uv_sync_runner

REPO = "https://github.com/owkin/hte.git"
REV = "76ce145f42fd37a91b389d8c8762de167647f82f"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="plumb-perrin-probe-") as tmp:
        checkout = resolve_git(REPO, REV, checkout_dir=Path(tmp) / "checkout")
        descriptor = describe_environment(checkout)
        print(f"tree: {checkout.tree_hash.scheme} {checkout.tree_hash.digest}")
        print(f"policy: {descriptor.policy}")
        print(f"python: {descriptor.python_pin} ({descriptor.python_pin_source})")
        print(f"policy detail: {descriptor.policy_detail}")
        build = build_environment(checkout, descriptor, runner=uv_sync_runner)
        print(f"build: ok={build.ok} policy={build.policy}")
        print(f"detail: {build.detail}")
        venv = checkout.checkout_dir / ".venv"
        if venv.is_dir():
            frozen = subprocess.run(
                ["uv", "pip", "freeze", "--python", str(venv / "bin" / "python")],
                capture_output=True, text=True, check=False,
            )
            packages = [line for line in frozen.stdout.splitlines() if line.strip()]
            print(f"frozen: {len(packages)} packages")
            print(f"python: {_python_version(venv)}")
        return 0 if build.ok else 1


def _python_version(venv: Path) -> str:
    result = subprocess.run(
        [str(venv / "bin" / "python"), "--version"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or result.stderr.strip()


if __name__ == "__main__":
    sys.exit(main())
