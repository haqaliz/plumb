"""The runner (R2): execute an entry point under the recorded posture.

`run_entrypoint(checkout, env_build, entrypoint, run_dir=..., timeout_seconds=...)`
runs the argv in a subprocess whose cwd is a **working copy of the checkout**
inside the run area — never the checkout itself, which for a local source is
the user's own directory. The copy preserves mtimes, so a committed output
stays older than the run and the capture layer's freshness guard (R3) can see
it for what it is.

Recorded causes, never silent: a non-zero exit or an unstartable argv is
`WONT_RUN`, an overrun is `TIMEOUT` (the whole process group is killed, so a
grandchild holding the pipes cannot hang the harness). A failed or missing env
build raises C2's `EnvBuildFailed` before anything runs.

Offline: every argv is the test interpreter (`sys.executable`) running a tiny
inline program in a tmp checkout.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

import pytest

from plumb.intake.causes import EnvBuildFailed
from plumb.intake.checkout import resolve_local
from plumb.intake.env import EnvBuild
from plumb.run.causes import TIMEOUT, WONT_RUN
from plumb.run.entrypoint import EntryPoint
from plumb.run.runner import run_entrypoint

OK_BUILD = EnvBuild(ok=True, policy="best-effort", detail="stub")


def make_checkout(root: Path, files: dict[str, bytes] | None = None):
    root.mkdir(parents=True, exist_ok=True)
    for rel, data in (files or {"README.md": b"# demo\n"}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return resolve_local(root)


def py(program: str) -> EntryPoint:
    return EntryPoint(argv=(sys.executable, "-c", program), source="explicit")


def run(tmp_path: Path, program: str, *, checkout=None, **kwargs):
    checkout = checkout or make_checkout(tmp_path / "proj")
    return run_entrypoint(
        checkout, OK_BUILD, py(program), run_dir=tmp_path / "run", **kwargs
    )


class TestASuccessfulRun:
    def test_stdout_and_exit_code_are_captured(self, tmp_path: Path) -> None:
        result = run(tmp_path, "print('hi')")
        assert result.stdout == b"hi\n"
        assert result.exit_code == 0
        assert result.failure is None

    def test_the_argv_and_timeout_are_recorded(self, tmp_path: Path) -> None:
        result = run(tmp_path, "print('hi')", timeout_seconds=42)
        assert result.entrypoint.argv == (sys.executable, "-c", "print('hi')")
        assert result.timeout_seconds == 42

    def test_the_start_time_brackets_the_run(self, tmp_path: Path) -> None:
        before = time.time_ns()
        result = run(tmp_path, "print('hi')")
        assert before <= result.started_at_ns <= time.time_ns()


class TestTheRunArea:
    def test_the_run_works_in_a_copy_not_the_checkout(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"data.txt": b"42\n"})
        result = run(
            tmp_path,
            "import os; print(os.getcwd()); print(open('data.txt').read().strip()); "
            "open('out.json', 'w').write('{}')",
            checkout=checkout,
        )
        cwd, data = result.stdout.decode().splitlines()
        assert Path(cwd).resolve() == result.workdir.resolve()
        assert result.workdir.resolve().is_relative_to((tmp_path / "run").resolve())
        assert data == "42"
        assert (result.workdir / "out.json").is_file()
        assert not (checkout.checkout_dir / "out.json").exists()

    def test_the_copy_preserves_mtimes(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {"results/out.json": b"{}"})
        old = 1_000_000_000
        os.utime(checkout.checkout_dir / "results/out.json", (old, old))
        result = run(tmp_path, "pass", checkout=checkout)
        copied = result.workdir / "results/out.json"
        assert copied.stat().st_mtime_ns == old * 10**9
        assert copied.stat().st_mtime_ns < result.started_at_ns

    def test_git_and_venv_are_not_copied(self, tmp_path: Path) -> None:
        checkout = make_checkout(
            tmp_path / "proj",
            {".git/HEAD": b"ref: refs/heads/main\n", ".venv/pyvenv.cfg": b"home = x\n", "a.py": b""},
        )
        result = run(tmp_path, "pass", checkout=checkout)
        assert (result.workdir / "a.py").is_file()
        assert not (result.workdir / ".git").exists()
        assert not (result.workdir / ".venv").exists()

    def test_a_non_empty_run_dir_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "run").mkdir()
        (tmp_path / "run" / "leftover").write_bytes(b"x")
        with pytest.raises(FileExistsError):
            run(tmp_path, "print('hi')")


class TestTheEnvPosture:
    def test_secret_bearing_variables_are_scrubbed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MY_API_KEY", "sk-do-not-leak")
        monkeypatch.setenv("PLUMB_HARMLESS", "kept")
        result = run(
            tmp_path,
            "import os; print(os.environ.get('MY_API_KEY')); print(os.environ.get('PLUMB_HARMLESS'))",
        )
        assert result.stdout.decode().splitlines() == ["None", "kept"]

    def test_uv_is_held_offline(self, tmp_path: Path) -> None:
        result = run(tmp_path, "import os; print(os.environ.get('UV_OFFLINE'))")
        assert result.stdout == b"1\n"

    def test_a_built_venv_in_the_checkout_is_the_run_environment(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj", {".venv/pyvenv.cfg": b"home = x\n"})
        venv = (checkout.checkout_dir / ".venv").resolve()
        result = run(
            tmp_path,
            "import os; print(os.environ['UV_PROJECT_ENVIRONMENT']); "
            "print(os.environ['VIRTUAL_ENV']); print(os.environ['PATH'].split(os.pathsep)[0])",
            checkout=checkout,
        )
        project_env, virtual_env, first_path = result.stdout.decode().splitlines()
        assert Path(project_env) == venv
        assert Path(virtual_env) == venv
        assert Path(first_path) == venv / "bin"

    def test_a_failed_env_build_runs_nothing(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj")
        failed = EnvBuild(ok=False, policy="lockfile", detail="uv sync failed")
        with pytest.raises(EnvBuildFailed):
            run_entrypoint(checkout, failed, py("print('hi')"), run_dir=tmp_path / "run")
        with pytest.raises(EnvBuildFailed):
            run_entrypoint(checkout, None, py("print('hi')"), run_dir=tmp_path / "run")
        assert not (tmp_path / "run").exists()


class TestRecordedFailures:
    def test_a_non_zero_exit_is_wont_run_with_the_exit_code(self, tmp_path: Path) -> None:
        result = run(tmp_path, "import sys; print('partial'); sys.stderr.write('boom'); sys.exit(3)")
        assert result.failure is not None
        assert result.failure.cause == WONT_RUN
        assert result.exit_code == 3
        assert "3" in result.failure.detail
        assert result.stdout == b"partial\n"
        assert result.stderr == b"boom"

    def test_an_unstartable_argv_is_wont_run(self, tmp_path: Path) -> None:
        checkout = make_checkout(tmp_path / "proj")
        entry = EntryPoint(argv=("plumb-no-such-executable-xyz",), source="explicit")
        result = run_entrypoint(checkout, OK_BUILD, entry, run_dir=tmp_path / "run")
        assert result.failure is not None
        assert result.failure.cause == WONT_RUN
        assert result.exit_code is None
        assert "plumb-no-such-executable-xyz" in result.failure.detail

    def test_an_overrun_is_timeout(self, tmp_path: Path) -> None:
        began = time.monotonic()
        result = run(
            tmp_path, "import time; print('started', flush=True); time.sleep(30)",
            timeout_seconds=0.5,
        )
        assert time.monotonic() - began < 10
        assert result.failure is not None
        assert result.failure.cause == TIMEOUT
        assert result.exit_code is None
        assert result.stdout == b"started\n"

    def test_a_grandchild_holding_the_pipes_cannot_hang_the_timeout(self, tmp_path: Path) -> None:
        program = (
            "import subprocess, sys, time; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
            "time.sleep(30)"
        )
        began = time.monotonic()
        result = run(tmp_path, program, timeout_seconds=0.5)
        assert time.monotonic() - began < 10
        assert result.failure is not None and result.failure.cause == TIMEOUT
