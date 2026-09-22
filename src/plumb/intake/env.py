"""Environment descriptor and the build-runner seam (I3).

`describe_environment(checkout)` records everything C3 needs to build a
reproducible environment and C6 to bundle the description:

- **Python pin** — from `.python-version`, else `pyproject.toml`'s
  `requires-python`, else the project default; the source of the pin is
  recorded, never silent.
- **Dependency policy** — lockfile-first (`uv.lock` → `uv sync`), else
  declared deps (`requirements*.txt`), else best-effort; the chosen policy is
  recorded.
- **Isolation posture** — the first-slice decision, recorded verbatim:
  subprocess runner, scrubbed env (secret-bearing variables removed), cwd =
  checkout, timeout; container isolation deferred.
- **Tool versions** — `git --version` and `uv --version`, probed offline at
  describe time (or supplied explicitly).

`build_environment(checkout, descriptor, runner=...)` is the seam that
executes the recorded policy. Tests pass a stub runner; the real `uv sync`
runs only through `tools/demo_env_build.py` at dev time. A failing runner —
whether it raises or reports failure — resolves to the named cause
`EnvBuildFailed`, never a silent pass. No runner at all is the offline guard:
the real build must be requested deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess

from plumb.intake.causes import EnvBuildFailed
from plumb.intake.checkout import Checkout
from plumb.intake.manifest import ManifestScan, scan_manifests

__all__ = [
    "EnvBuild",
    "EnvDescriptor",
    "build_environment",
    "describe_environment",
    "uv_sync_runner",
]

#: The project's floor (`pyproject.toml` requires-python >= 3.11), used when a
#: checkout records no python pin at all.
_DEFAULT_PYTHON_PIN = "3.11"

#: First-slice isolation posture (ARCHITECTURE.md open question, decided here):
#: a subprocess on the user's compute with a scrubbed env, cwd = checkout, a
#: timeout, and no network beyond the env build itself (pull-only). Container
#: isolation is a named follow-on.
_ISOLATION_POSTURE = (
    "subprocess runner; cwd = checkout; env scrubbed (secret-bearing variables "
    "removed); timeout 1800s; no network except the recorded env build itself "
    "(pull-only, never egress); container isolation deferred"
)

_REQUIRES_PYTHON = re.compile(r'requires-python\s*=\s*["\']([^"\']+)["\']')

#: Environment-variable name fragments considered secret-bearing and scrubbed
#: from the runner's env, so a build command never inherits the user's keys.
_SECRET_FRAGMENTS = (
    "API_KEY",
    "AUTH",
    "PASSWORD",
    "PASSWD",
    "PRIVATE_KEY",
    "SECRET",
    "TOKEN",
)


@dataclass(frozen=True)
class EnvDescriptor:
    """A reproducible description of how to build the checkout's environment."""

    python_pin: str
    python_pin_source: str  # ".python-version" | "pyproject.toml" | "default"
    policy: str  # "lockfile" | "declared" | "best-effort"
    policy_detail: str
    isolation_posture: str
    tool_versions: tuple[tuple[str, str], ...]  # sorted (tool, version) pairs
    manifests: ManifestScan


@dataclass(frozen=True)
class EnvBuild:
    """The outcome of running the recorded policy through a runner."""

    ok: bool
    policy: str
    detail: str


def describe_environment(
    checkout: Checkout,
    *,
    tool_versions: dict[str, str] | None = None,
) -> EnvDescriptor:
    """Record the python pin, dependency policy, posture, and tool versions."""
    manifests = scan_manifests(checkout)
    python_pin, python_pin_source = _python_pin(checkout.checkout_dir)
    policy, policy_detail = _dependency_policy(manifests)
    versions = tuple(
        sorted((tool_versions or _probe_tool_versions()).items())
    )
    return EnvDescriptor(
        python_pin=python_pin,
        python_pin_source=python_pin_source,
        policy=policy,
        policy_detail=policy_detail,
        isolation_posture=_ISOLATION_POSTURE,
        tool_versions=versions,
        manifests=manifests,
    )


def build_environment(
    checkout: Checkout,
    descriptor: EnvDescriptor,
    *,
    runner=None,
) -> EnvBuild:
    """Execute the recorded policy through `runner`; failures are named causes.

    `runner` is a callable ``(checkout, descriptor) -> EnvBuild``. No runner is
    the offline guard: the real build must be requested deliberately via
    `tools/demo_env_build.py` (dev time only, never tests or CI).
    """
    if runner is None:
        raise EnvBuildFailed(
            "no env runner supplied; the real build (uv sync) runs only via "
            "tools/demo_env_build.py at dev time, never in tests or CI"
        )
    try:
        build = runner(checkout, descriptor)
    except Exception as exc:
        raise EnvBuildFailed(
            f"environment build failed under policy {descriptor.policy!r}: {exc}"
        ) from exc
    if build is None or not build.ok:
        detail = getattr(build, "detail", "runner returned no result")
        raise EnvBuildFailed(
            f"environment build failed under policy {descriptor.policy!r}: {detail}"
        )
    return build


def uv_sync_runner(
    checkout: Checkout,
    descriptor: EnvDescriptor,
    *,
    timeout_seconds: int = 1800,
) -> EnvBuild:
    """The real (dev-time) runner: executes the recorded policy via `uv`.

    Runs only when explicitly requested — `tools/demo_env_build.py` is the
    only caller in this repo. `uv sync` is pull-only (installs the checkout's
    pinned deps) and never egresses user data (constraint #2).
    """
    command = _policy_command(checkout, descriptor)
    result = subprocess.run(
        command,
        cwd=str(checkout.checkout_dir),
        env=_scrubbed_env(),
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    out = result.stdout.decode("utf-8", "replace").strip()
    err = result.stderr.decode("utf-8", "replace").strip()
    if result.returncode != 0:
        detail = err or out or "uv exited non-zero"
        return EnvBuild(ok=False, policy=descriptor.policy, detail=detail)
    return EnvBuild(ok=True, policy=descriptor.policy, detail=out or err)


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


def _python_pin(checkout_dir: Path) -> tuple[str, str]:
    version_file = checkout_dir / ".python-version"
    if version_file.is_file():
        content = version_file.read_text(encoding="utf-8").strip()
        if content:
            return content, ".python-version"
    pyproject = checkout_dir / "pyproject.toml"
    if pyproject.is_file():
        match = _REQUIRES_PYTHON.search(pyproject.read_text(encoding="utf-8"))
        if match:
            return match.group(1), "pyproject.toml"
    return _DEFAULT_PYTHON_PIN, "default"


def _dependency_policy(manifests: ManifestScan) -> tuple[str, str]:
    if manifests.uv_lock is not None:
        return "lockfile", "uv sync (uv.lock present)"
    if manifests.requirements:
        names = ", ".join(str(path) for path in manifests.requirements)
        return "declared", f"install declared deps ({names})"
    return (
        "best-effort",
        "no lockfile or declared deps; best-effort resolve recorded as such",
    )


def _probe_tool_versions() -> dict[str, str]:
    return {
        "git": _probe_version(["git", "--version"]),
        "uv": _probe_version(["uv", "--version"]),
    }


def _probe_version(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, timeout=60, check=False
        )
    except OSError as exc:
        return f"unavailable ({exc})"
    if result.returncode != 0:
        return "unavailable"
    text = result.stdout.decode("utf-8", "replace").strip()
    return text or result.stderr.decode("utf-8", "replace").strip() or "unavailable"


def _scrubbed_env() -> dict[str, str]:
    """The user's environment with secret-bearing variables removed."""
    scrubbed = dict(os.environ)
    for key in list(scrubbed):
        upper = key.upper()
        if any(fragment in upper for fragment in _SECRET_FRAGMENTS):
            del scrubbed[key]
    return scrubbed


def _policy_command(checkout: Checkout, descriptor: EnvDescriptor) -> list[str]:
    """The uv command that executes the recorded policy."""
    project = ["--project", str(checkout.checkout_dir)]
    if descriptor.policy == "lockfile":
        return ["uv", "sync", *project]
    if descriptor.policy == "declared":
        return ["uv", "pip", "install", *[str(path) for path in descriptor.manifests.requirements]]
    return ["uv", "sync", *project]