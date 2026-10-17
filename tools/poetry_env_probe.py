#!/usr/bin/env python3
"""Dev-time probe of the C2 poetry environment policy.

Resolves a poetry-locked checkout, records its environment descriptor, builds
its **real** environment through the engine runner
(`build_environment(checkout, descriptor, runner=uv_sync_runner)`), then prints
the recorded policy, its detail, and `uv pip freeze` from the built
`checkout/.venv` as evidence. It is the hand-run proof that a poetry repo is
classified `"poetry"` (not `"best-effort"`) and builds non-empty.

The default target is Perrin (`owkin/hte`), the one committed poetry case; pass
`--repo` (a local path or https git URL) and, for a git URL, `--rev` to probe
another poetry checkout.

This builds from the network at dev time only (`git clone` from GitHub and
package downloads from PyPI) — it is never run in tests or CI. A failing build
is reported as its named cause (`EnvBuildFailed`) and a non-zero exit, never a
silent pass.

Never imported by tests. Run by hand: `uv run tools/poetry_env_probe.py`

Paste the output into the PR description as the probe evidence.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

from plumb.intake import (
    EnvBuildFailed,
    RevNotFound,
    SourceNotFound,
    build_environment,
    describe_environment,
    resolve_git,
    resolve_local,
    uv_sync_runner,
)

DEFAULT_REPO = "https://github.com/owkin/hte.git"
DEFAULT_REV = "76ce145f42fd37a91b389d8c8762de167647f82f"

_GIT_URL_PREFIXES = ("http://", "https://", "ssh://", "git://", "git@")


def _is_git_url(repo: str) -> bool:
    return repo.startswith(_GIT_URL_PREFIXES) or repo.endswith(".git")


def freeze(python: Path) -> list[str]:
    """`uv pip freeze` against the built environment's interpreter — the evidence."""
    result = subprocess.run(
        ["uv", "pip", "freeze", "--python", str(python)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="poetry_env_probe.py",
        description=(
            "Build a poetry-locked checkout's environment through the engine runner "
            "and print the policy + uv pip freeze (dev time; needs the network)."
        ),
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help="local path or https git URL (default: Perrin, owkin/hte)",
    )
    parser.add_argument(
        "--rev",
        default=DEFAULT_REV,
        help="git revision to pin; used only for a git URL (default: Perrin's paper-era rev)",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="plumb-poetry-probe-") as tmp:
        root = Path(tmp)
        try:
            if _is_git_url(args.repo):
                checkout = resolve_git(args.repo, args.rev, checkout_dir=root / "checkout")
            else:
                checkout = resolve_local(args.repo)
        except (SourceNotFound, RevNotFound) as exc:
            print(f"resolve failed ({type(exc).__name__}): {exc}", file=sys.stderr)
            return 1

        descriptor = describe_environment(checkout)

        print(f"repo:          {args.repo}")
        if checkout.source.kind == "git":
            print(f"rev:           {checkout.source.rev_resolved}")
        print(f"checkout:      {checkout.checkout_dir}")
        print(f"tree hash:     {checkout.tree_hash.scheme} {checkout.tree_hash.digest}")
        print(f"python pin:    {descriptor.python_pin} (from {descriptor.python_pin_source})")
        print(f"policy:        {descriptor.policy}")
        print(f"policy detail: {descriptor.policy_detail}")

        if descriptor.policy != "poetry":
            print(
                f"expected policy 'poetry' for a poetry-locked repo, got "
                f"{descriptor.policy!r} — the poetry policy is not present in this tree",
                file=sys.stderr,
            )
            return 1

        print("\nrunning the real poetry build through the engine runner (dev time, network) ...")
        try:
            build = build_environment(checkout, descriptor, runner=uv_sync_runner)
        except EnvBuildFailed as exc:
            print(f"env build failed (EnvBuildFailed): {exc}", file=sys.stderr)
            return 1

        print(f"  env build:    ok={build.ok} policy={build.policy}")
        print(f"  build detail: {build.detail.splitlines()[-1] if build.detail else ''}")

        python = checkout.checkout_dir / ".venv" / "bin" / "python"
        if not python.exists():
            print(f"no built interpreter at {python}", file=sys.stderr)
            return 1

        print("\nuv pip freeze (evidence):")
        for line in freeze(python):
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
