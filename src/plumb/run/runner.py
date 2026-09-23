"""The runner: execute an entry point under the recorded posture (R2).

`run_entrypoint(checkout, env_build, entrypoint, ...)` runs the argv on the
user's compute and returns a `RunResult` — what ran, when it started, what it
wrote to stdout/stderr, how it exited, and the named cause if it failed.

**The run area.** Every run gets a fresh run directory (refused if it already
holds anything) and works in a copy of the checkout at ``<run_dir>/work``.
The run never executes in the checkout itself: for a local source that is the
user's own directory, and a pinned checkout must stay byte-identical to its
recorded tree hash for replay. The copy preserves mtimes (``copy2``), so a
committed output is still older than the run start and the capture layer's
freshness guard sees it as stale. ``.git`` is not copied (bookkeeping, not
the tree), nor is ``.venv`` (a built env is used in place, see below).

**The posture** is C2's, recorded in its `EnvDescriptor`: a subprocess with a
scrubbed env (secret-bearing variables removed), a timeout, and no network —
``UV_OFFLINE=1`` holds `uv` to the environment already built. When the
checkout carries a built ``.venv``, it is the run's environment
(``UV_PROJECT_ENVIRONMENT``, ``VIRTUAL_ENV``, and its ``bin`` first on
``PATH``), so ``python main.py`` and ``uv run <script>`` both resolve there.

**Recorded causes, never silent.** A non-zero exit or an argv that cannot
start is `WONT_RUN`; an overrun is `TIMEOUT`. The child runs in its own
session and a timeout kills the whole process group, so a grandchild holding
the output pipes cannot hang the harness (POSIX only). A missing or failed env
build raises C2's `EnvBuildFailed` before anything is copied or run.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from plumb.intake.causes import EnvBuildFailed
from plumb.intake.checkout import Checkout
from plumb.intake.env import EnvBuild, _scrubbed_env
from plumb.run.causes import TIMEOUT, WONT_RUN
from plumb.run.entrypoint import EntryPoint

__all__ = ["RunFailure", "RunResult", "run_entrypoint"]

#: Matches the timeout recorded in C2's isolation posture.
_DEFAULT_TIMEOUT_SECONDS = 1800

#: Not copied into the working copy: version-control bookkeeping, and a built
#: env that is used in place rather than duplicated.
_NOT_COPIED = (".git", ".venv")


@dataclass(frozen=True)
class RunFailure:
    """A recorded failure: the named cause and what happened."""

    cause: str  # WONT_RUN | TIMEOUT
    detail: str


@dataclass(frozen=True)
class RunResult:
    """What ran, when, and what came out of it."""

    entrypoint: EntryPoint
    env_policy: str
    run_dir: Path  # absolute; the run area on the user's compute, never recorded
    workdir: Path  # absolute; the run's working copy of the checkout
    started_at_ns: int  # wall clock just before the process started
    timeout_seconds: float
    exit_code: int | None  # None when the process never started or was killed
    stdout: bytes
    stderr: bytes
    failure: RunFailure | None


def run_entrypoint(
    checkout: Checkout,
    env_build: EnvBuild | None,
    entrypoint: EntryPoint,
    *,
    run_dir: Path | str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> RunResult:
    """Run `entrypoint` in a working copy of `checkout`; failures are recorded."""
    if env_build is None or not env_build.ok:
        detail = getattr(env_build, "detail", "no env build supplied")
        raise EnvBuildFailed(f"refusing to run without a built environment: {detail}")

    run_dir = _fresh_run_dir(checkout, run_dir)
    workdir = run_dir / "work"
    shutil.copytree(
        checkout.checkout_dir,
        workdir,
        symlinks=True,
        ignore=shutil.ignore_patterns(*_NOT_COPIED),
    )
    env = _run_env(checkout)

    def result(exit_code, stdout, stderr, failure) -> RunResult:
        return RunResult(
            entrypoint=entrypoint,
            env_policy=env_build.policy,
            run_dir=run_dir,
            workdir=workdir,
            started_at_ns=started_at_ns,
            timeout_seconds=timeout_seconds,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            failure=failure,
        )

    # Taken after the copy: the copied files keep their original mtimes, so
    # everything the checkout already held is strictly older than this.
    started_at_ns = time.time_ns()
    try:
        process = subprocess.Popen(
            list(entrypoint.argv),
            cwd=str(workdir),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        return result(
            None, b"", b"", RunFailure(WONT_RUN, f"could not start {entrypoint.argv[0]!r}: {exc}")
        )

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_group(process)
        stdout, stderr = process.communicate()
        return result(
            None, stdout, stderr,
            RunFailure(TIMEOUT, f"killed after {timeout_seconds}s timeout"),
        )

    if process.returncode != 0:
        return result(
            process.returncode, stdout, stderr,
            RunFailure(WONT_RUN, f"exited with code {process.returncode}"),
        )
    return result(0, stdout, stderr, None)


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


def _fresh_run_dir(checkout: Checkout, explicit: Path | str | None) -> Path:
    if explicit is None:
        explicit = Path("runs") / f"{checkout.tree_hash.digest[:12]}-{time.time_ns()}"
    run_dir = Path(explicit).resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(
            f"run directory already exists and is not empty: {run_dir} — "
            "refusing to run over a previous run's outputs"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _run_env(checkout: Checkout) -> dict[str, str]:
    env = _scrubbed_env()
    env["UV_OFFLINE"] = "1"
    venv = checkout.checkout_dir.resolve() / ".venv"
    if venv.is_dir():
        env["UV_PROJECT_ENVIRONMENT"] = str(venv)
        env["VIRTUAL_ENV"] = str(venv)
        env["PATH"] = os.pathsep.join([str(venv / "bin"), env.get("PATH", "")])
    return env


def _kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
