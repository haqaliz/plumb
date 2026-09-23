#!/usr/bin/env python3
"""Recorded dev-time demo of C2 artifact intake + the real environment build.

Creates a tiny local git repo with a hello-world package (pyproject.toml and a
generated uv.lock), resolves it via `resolve_git` over a `file://` URL,
describes its environment, and runs the **real** `uv sync` through the
`uv_sync_runner` — the only place in the repo the real build runs. Tests never
import this module and never run the real build (`tests/conftest.py` blocks
sockets; the runner seam is stubbed in `tests/intake/test_env.py`).

Run by hand:
    uv run tools/demo_env_build.py

The descriptor output below is the evidence that intake → describe → build is
wired end to end; paste it into the PR description (I4).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from plumb.intake import (
    build_environment,
    describe_environment,
    resolve_git,
    uv_sync_runner,
)

_PYPROJECT = """\
[project]
name = "hello-plumb-demo"
version = "0.1.0"
description = "A hello-world package for the Plumb env-build demo"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/hello_plumb_demo"]
"""

GIT_ENV = ["-c", "user.name=Plumb Demo", "-c", "user.email=demo@plumb.local"]


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *GIT_ENV, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=300,
    )


def make_demo_repo() -> Path:
    """A tiny local git repo with a hello-world package and a uv.lock."""
    repo = Path(tempfile.mkdtemp(prefix="plumb-demo-")) / "hello-plumb-demo"
    repo.mkdir(parents=True)
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    pkg = repo / "src" / "hello_plumb_demo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        'def greet() -> str:\n'
        '    return "hello from plumb\'s artifact-intake demo"\n',
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# hello-plumb-demo\n", encoding="utf-8")
    (repo / ".python-version").write_text("3.12\n", encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "hello-world package")
    # Generate the lockfile the descriptor's lockfile-first policy keys on.
    subprocess.run(
        ["uv", "lock", "--offline"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=300,
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "lock deps")
    return repo


def main() -> int:
    repo = make_demo_repo()
    print(f"demo repo: {repo}")
    print("resolving file:// URL ...")
    checkout = resolve_git(repo.as_uri(), checkout_dir=repo.parent / "checkout")
    print(f"  checkout dir: {checkout.checkout_dir}")
    print(f"  tree hash:    {checkout.tree_hash.scheme} {checkout.tree_hash.digest}")
    print(
        f"  source:       git {checkout.source.location} "
        f"rev {checkout.source.rev_resolved}"
        f"{' (default branch)' if checkout.source.rev_defaulted else ''}"
    )
    descriptor = describe_environment(checkout)
    print("\nenvironment descriptor:")
    print(f"  python pin:    {descriptor.python_pin} (from {descriptor.python_pin_source})")
    print(f"  policy:        {descriptor.policy} — {descriptor.policy_detail}")
    print(f"  manifests:     uv.lock={descriptor.manifests.uv_lock} "
          f"pyproject={descriptor.manifests.pyproject} "
          f"requirements={descriptor.manifests.requirements}")
    print(f"  posture:       {descriptor.isolation_posture}")
    print(
        "  tool versions: "
        + "; ".join(f"{name}={version}" for name, version in descriptor.tool_versions)
    )
    print("\nrunning the real uv sync (dev time only) ...")
    build = build_environment(checkout, descriptor, runner=uv_sync_runner)
    print(f"  env build:     ok={build.ok} policy={build.policy}")
    print(f"  build detail:  {build.detail.splitlines()[-1] if build.detail else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())