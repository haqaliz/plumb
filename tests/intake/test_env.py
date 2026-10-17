"""Manifest scan and environment descriptor (I3).

`scan_manifests(checkout)` records what a repo *looks like* — the manifest
files present — so C3 can later pick entry points. `describe_environment`
turns that into a reproducible `EnvDescriptor`: a python pin (`.python-version`
→ `pyproject.toml` → default, source recorded), a dependency policy chosen
lockfile-first → declared → best-effort (with the policy recorded, never
silent), the isolation posture, and the external tool versions. The runner
seam `build_environment` executes the recorded policy through a supplied
runner; in tests that runner is a stub, and the real `uv sync` runs only in
`tools/demo_env_build.py` at dev time.

Nothing here touches the network: manifest scanning reads the checkout, tool
version probes are `--version` subprocesses, and the stub runner is a
callback.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from plumb.intake.causes import EnvBuildFailed
from plumb.intake.checkout import resolve_local
from plumb.intake.env import (
    _DEFAULT_PYTHON_PIN,
    EnvBuild,
    build_environment,
    describe_environment,
    uv_sync_runner,
)
from plumb.intake.manifest import scan_manifests

_THIS_DIR = Path(__file__).parent
_SRC = _THIS_DIR.parents[1] / "src"

_POETRY_SEEDS = ("0", "1", "12345", "random")

_CHILD_PROGRAM = """\
import sys

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])

from test_env import child_main

child_main()
"""


def child_main() -> None:
    import tempfile

    from plumb.intake.env import describe_environment

    root = Path(tempfile.mkdtemp()) / "proj"
    root.mkdir(parents=True)
    (root / "poetry.lock").write_bytes(b"# lock\n")
    descriptor = describe_environment(
        resolve_local(root),
        tool_versions={"git": "git version 2.47.0", "uv": "uv 0.5.0"},
    )
    sys.stdout.buffer.write(descriptor.to_text().encode("utf-8"))



def make_checkout(root: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


ALL_MANIFESTS = {
    "uv.lock": b"version = 1\n",
    "pyproject.toml": b'[project]\nrequires-python = ">=3.11"\n',
    "requirements.txt": b"numpy==2.0\n",
    "requirements-dev.txt": b"pytest==8.0\n",
    "environment.yml": b"name: demo\n",
    "Makefile": b"all:\n\techo hi\n",
    "main.py": b"print('hi')\n",
    "analysis.ipynb": b'{"cells": []}\n',
}


class TestScanManifests:
    def test_detects_every_manifest_present(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", ALL_MANIFESTS)
        checkout = resolve_local(checkout_dir)
        scan = scan_manifests(checkout)
        assert scan.uv_lock == Path("uv.lock")
        assert scan.pyproject == Path("pyproject.toml")
        assert scan.requirements == (Path("requirements-dev.txt"), Path("requirements.txt"))
        assert scan.environment_yml == Path("environment.yml")
        assert scan.makefile == Path("Makefile")
        assert scan.main_py == Path("main.py")
        assert scan.notebooks == (Path("analysis.ipynb"),)

    def test_reports_absence_as_none(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "empty", {"notes.md": b"hi"})
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.uv_lock is None
        assert scan.pyproject is None
        assert scan.requirements == ()
        assert scan.environment_yml is None
        assert scan.makefile is None
        assert scan.main_py is None
        assert scan.notebooks == ()

    def test_does_not_look_inside_subdirectories(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {"sub/pyproject.toml": b"[project]\n", "sub/uv.lock": b"", "sub/analysis.ipynb": b"{}\n"},
        )
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.pyproject is None
        assert scan.uv_lock is None
        assert scan.notebooks == ()

    def test_notebooks_are_root_only(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {
                "sub/analysis.ipynb": b'{"cells": []}\n',
                ".ipynb_checkpoints/analysis.ipynb": b'{"cells": []}\n',
            },
        )
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.notebooks == ()

    def test_notebooks_are_sorted(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {"b.ipynb": b'{"cells": []}\n', "a.ipynb": b'{"cells": []}\n'},
        )
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.notebooks == (Path("a.ipynb"), Path("b.ipynb"))

    def test_requirements_globs_only_at_the_root(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {"requirements.txt": b"", "sub/requirements.txt": b"", "requirements-prod.txt": b""},
        )
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.requirements == (Path("requirements-prod.txt"), Path("requirements.txt"))

    def test_detects_a_poetry_lock(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"poetry.lock": b"# lock\n"})
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.poetry_lock == Path("poetry.lock")

    def test_a_poetry_lock_is_reported_absent_as_none(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"notes.md": b"hi"})
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.poetry_lock is None

    def test_a_poetry_lock_is_root_only(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"sub/poetry.lock": b"# lock\n"})
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.poetry_lock is None


class TestDependencyPolicy:
    def test_lockfile_wins_when_uv_lock_is_present(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {"uv.lock": b"version = 1\n", "pyproject.toml": b'[project]\nrequires-python = ">=3.11"\n'},
        )
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.policy == "lockfile"
        assert "uv sync" in descriptor.policy_detail

    def test_declared_deps_when_only_requirements_exist(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"requirements.txt": b"numpy==2.0\n"})
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.policy == "declared"
        assert "requirements.txt" in descriptor.policy_detail

    def test_pyproject_without_a_lockfile_is_best_effort(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj", {"pyproject.toml": b'[project]\nrequires-python = ">=3.11"\n'}
        )
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.policy == "best-effort"

    def test_neither_lockfile_nor_requirements_is_best_effort_recorded(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"main.py": b"print('hi')\n"})
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.policy == "best-effort"
        assert "best-effort" in descriptor.policy_detail

    def test_a_poetry_lock_is_the_poetry_policy(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"poetry.lock": b"# lock\n"})
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.policy == "poetry"
        assert "poetry.lock" in descriptor.policy_detail

    def test_uv_lock_beats_a_poetry_lock(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj", {"uv.lock": b"version = 1\n", "poetry.lock": b"# lock\n"}
        )
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.policy == "lockfile"

    def test_poetry_beats_requirements(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj", {"poetry.lock": b"# lock\n", "requirements.txt": b"numpy==2.0\n"}
        )
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.policy == "poetry"


class TestDescriptorDeterminism:
    def test_the_poetry_render_is_byte_identical_across_processes(self) -> None:
        outputs = {}
        for seed in _POETRY_SEEDS:
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
            result = subprocess.run(
                [sys.executable, "-c", _CHILD_PROGRAM, str(_THIS_DIR), str(_SRC)],
                env=env,
                capture_output=True,
                timeout=120,
                check=False,
            )
            assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
            outputs[seed] = result.stdout
        assert len(set(outputs.values())) == 1, outputs
        assert b"resolved by 'poetry'" in outputs["0"]

    def test_the_best_effort_render_is_unchanged(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"main.py": b"print('hi')\n"})
        descriptor = describe_environment(
            resolve_local(checkout_dir),
            tool_versions={"git": "git version 2.47.0", "uv": "uv 0.5.0"},
        )
        assert descriptor.to_text() == (
            "# resolved by 'best-effort' (no lockfile or declared deps; best-effort "
            "resolve recorded as such) on python pin '3.11' (default); isolation: "
            "subprocess runner; cwd = checkout; env scrubbed (secret-bearing "
            "variables removed); timeout 1800s; no network except the recorded env "
            "build itself (pull-only, never egress); container isolation deferred; "
            "tools: git=git version 2.47.0, uv=uv 0.5.0"
        )


class TestPolicyCommands:
    @staticmethod
    def _env_module():
        return importlib.import_module("plumb.intake.env")

    def _descriptor(self, checkout_dir: Path):
        return describe_environment(resolve_local(checkout_dir), tool_versions={})

    def test_a_poetry_checkout_builds_via_uv_venv_then_uv_pip_install(self, tmp_path: Path) -> None:
        env_module = self._env_module()
        checkout_dir = make_checkout(tmp_path / "proj", {"poetry.lock": b"# lock\n"})
        checkout = resolve_local(checkout_dir)
        commands = env_module._policy_commands(checkout, self._descriptor(checkout_dir))
        assert len(commands) == 2
        venv_command, install_command = commands
        assert venv_command[:2] == ["uv", "venv"]
        assert install_command[:3] == ["uv", "pip", "install"]
        assert "--python" in install_command
        assert install_command[-1] == str(checkout.checkout_dir)

    def test_a_lockfile_checkout_is_a_single_uv_sync(self, tmp_path: Path) -> None:
        env_module = self._env_module()
        checkout_dir = make_checkout(tmp_path / "proj", {"uv.lock": b"version = 1\n"})
        checkout = resolve_local(checkout_dir)
        commands = env_module._policy_commands(checkout, self._descriptor(checkout_dir))
        assert len(commands) == 1
        assert commands[0][:2] == ["uv", "sync"]
        assert "--project" in commands[0]

    def test_a_best_effort_checkout_is_a_single_uv_sync(self, tmp_path: Path) -> None:
        env_module = self._env_module()
        checkout_dir = make_checkout(tmp_path / "proj", {"main.py": b"print('hi')\n"})
        checkout = resolve_local(checkout_dir)
        commands = env_module._policy_commands(checkout, self._descriptor(checkout_dir))
        assert len(commands) == 1
        assert commands[0][:2] == ["uv", "sync"]

    def test_a_concrete_python_pin_is_passed_to_uv_venv(self, tmp_path: Path) -> None:
        env_module = self._env_module()
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {"poetry.lock": b"# lock\n", ".python-version": b"3.10\n"},
        )
        checkout = resolve_local(checkout_dir)
        commands = env_module._policy_commands(checkout, self._descriptor(checkout_dir))
        assert commands[0] == [
            "uv",
            "venv",
            "--python",
            "3.10",
            str(checkout.checkout_dir.resolve() / ".venv"),
        ]

    def test_a_specifier_python_pin_is_not_passed_to_uv_venv(self, tmp_path: Path) -> None:
        env_module = self._env_module()
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {
                "poetry.lock": b"# lock\n",
                "pyproject.toml": b'[project]\nrequires-python = ">=3.9"\n',
            },
        )
        checkout = resolve_local(checkout_dir)
        descriptor = self._descriptor(checkout_dir)
        assert descriptor.python_pin == ">=3.9"
        commands = env_module._policy_commands(checkout, descriptor)
        assert commands[0] == ["uv", "venv", str(checkout.checkout_dir.resolve() / ".venv")]


class TestPythonPin:
    def test_python_version_file_wins(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {
                ".python-version": b"3.12\n",
                "pyproject.toml": b'[project]\nrequires-python = ">=3.11"\n',
            },
        )
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.python_pin == "3.12"
        assert descriptor.python_pin_source == ".python-version"

    def test_pyproject_requires_python_next(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {"pyproject.toml": b'[project]\nrequires-python = ">=3.11"\n'},
        )
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.python_pin == ">=3.11"
        assert descriptor.python_pin_source == "pyproject.toml"

    def test_default_is_recorded_as_such(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"main.py": b"print('hi')\n"})
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.python_pin == _DEFAULT_PYTHON_PIN
        assert descriptor.python_pin_source == "default"


class TestIsolationPostureAndToolVersions:
    def test_the_posture_string_is_recorded_and_specific(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"uv.lock": b"", "pyproject.toml": b"[project]\n"})
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        posture = descriptor.isolation_posture.lower()
        assert "subprocess" in posture
        assert "scrubbed" in posture
        assert "timeout" in posture
        assert "container" in posture

    def test_tool_versions_are_probed_offline(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"main.py": b"print('hi')\n"})
        descriptor = describe_environment(resolve_local(checkout_dir))
        versions = dict(descriptor.tool_versions)
        assert "git" in versions and versions["git"]
        assert "uv" in versions and versions["uv"]

    def test_explicit_tool_versions_are_honoured(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", {"main.py": b"print('hi')\n"})
        descriptor = describe_environment(
            resolve_local(checkout_dir), tool_versions={"git": "git version 2.47.0", "uv": "uv 0.5.0"}
        )
        assert dict(descriptor.tool_versions) == {
            "git": "git version 2.47.0",
            "uv": "uv 0.5.0",
        }

    def test_the_descriptor_records_the_manifests(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "proj", ALL_MANIFESTS)
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        assert descriptor.manifests.uv_lock is not None
        assert descriptor.manifests.main_py is not None


class TestBuildEnvironment:
    def _descriptor(self, tmp_path: Path, files: dict[str, bytes]) -> tuple[Path, object]:
        checkout_dir = make_checkout(tmp_path / "proj", files)
        descriptor = describe_environment(resolve_local(checkout_dir), tool_versions={})
        return checkout_dir, descriptor

    def test_a_successful_stub_runner_returns_the_build(self, tmp_path: Path) -> None:
        checkout_dir, descriptor = self._descriptor(tmp_path, {"uv.lock": b"", "pyproject.toml": b"[project]\n"})

        def ok_runner(checkout, desc) -> EnvBuild:
            assert checkout.checkout_dir == checkout_dir
            assert desc.policy == descriptor.policy
            return EnvBuild(ok=True, policy=desc.policy, detail="stub ok")

        build = build_environment(resolve_local(checkout_dir), descriptor, runner=ok_runner)
        assert build.ok
        assert build.policy == "lockfile"

    def test_a_raising_stub_is_a_named_cause(self, tmp_path: Path) -> None:
        checkout_dir, descriptor = self._descriptor(tmp_path, {"requirements.txt": b"numpy\n"})

        def boom_runner(checkout, desc):
            raise RuntimeError("stub boom")

        with pytest.raises(EnvBuildFailed):
            build_environment(resolve_local(checkout_dir), descriptor, runner=boom_runner)

    def test_a_stub_that_reports_failure_is_a_named_cause(self, tmp_path: Path) -> None:
        checkout_dir, descriptor = self._descriptor(tmp_path, {"main.py": b"print('hi')\n"})

        def failing_runner(checkout, desc) -> EnvBuild:
            return EnvBuild(ok=False, policy=desc.policy, detail="stub failed")

        with pytest.raises(EnvBuildFailed):
            build_environment(resolve_local(checkout_dir), descriptor, runner=failing_runner)

    def test_no_runner_is_an_offline_named_cause(self, tmp_path: Path) -> None:
        checkout_dir, descriptor = self._descriptor(tmp_path, {"uv.lock": b"", "pyproject.toml": b"[project]\n"})
        with pytest.raises(EnvBuildFailed):
            build_environment(resolve_local(checkout_dir), descriptor)


def _fake_uv_success(*args, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")


def _checkout_with_venv(
    root: Path, files: dict[str, bytes], *, populated: bool
) -> Path:
    checkout_dir = make_checkout(root, files)
    site = checkout_dir / ".venv" / "lib" / "python3.11" / "site-packages"
    site.mkdir(parents=True)
    if populated:
        (site / "foo-1.0.dist-info").mkdir()
    return checkout_dir


def _descriptor(checkout):
    return describe_environment(checkout, tool_versions={"git": "git version 2.47.0", "uv": "uv 0.5.0"})


def _assert_the_empty_environment_is_refused(checkout, descriptor) -> None:
    build = uv_sync_runner(checkout, descriptor)
    assert not build.ok, "an empty environment was recorded as a build"


class TestEmptyEnvironmentGuard:
    def test_an_empty_environment_is_not_a_build(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_module = importlib.import_module("plumb.intake.env")
        monkeypatch.setattr(env_module.subprocess, "run", _fake_uv_success)
        checkout_dir = _checkout_with_venv(tmp_path / "proj", {"poetry.lock": b"# lock\n"}, populated=False)
        checkout = resolve_local(checkout_dir)
        descriptor = _descriptor(checkout)
        assert descriptor.policy == "poetry"
        build = uv_sync_runner(checkout, descriptor)
        assert build.ok is False
        assert "empty" in build.detail
        with pytest.raises(EnvBuildFailed):
            build_environment(checkout, descriptor, runner=uv_sync_runner)

    def test_an_empty_lockfile_environment_is_not_a_build(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_module = importlib.import_module("plumb.intake.env")
        monkeypatch.setattr(env_module.subprocess, "run", _fake_uv_success)
        checkout_dir = _checkout_with_venv(
            tmp_path / "proj", {"uv.lock": b"version = 1\n"}, populated=False
        )
        checkout = resolve_local(checkout_dir)
        descriptor = _descriptor(checkout)
        assert descriptor.policy == "lockfile"
        assert uv_sync_runner(checkout, descriptor).ok is False

    def test_a_populated_environment_is_a_build(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_module = importlib.import_module("plumb.intake.env")
        monkeypatch.setattr(env_module.subprocess, "run", _fake_uv_success)
        checkout_dir = _checkout_with_venv(tmp_path / "proj", {"poetry.lock": b"# lock\n"}, populated=True)
        checkout = resolve_local(checkout_dir)
        descriptor = _descriptor(checkout)
        assert uv_sync_runner(checkout, descriptor).ok is True

    def test_best_effort_empty_is_not_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_module = importlib.import_module("plumb.intake.env")
        monkeypatch.setattr(env_module.subprocess, "run", _fake_uv_success)
        checkout_dir = _checkout_with_venv(tmp_path / "proj", {"main.py": b"print('hi')\n"}, populated=False)
        checkout = resolve_local(checkout_dir)
        descriptor = _descriptor(checkout)
        assert descriptor.policy == "best-effort"
        assert uv_sync_runner(checkout, descriptor).ok is True

    def test_a_missing_site_packages_is_empty(self, tmp_path: Path) -> None:
        env_module = importlib.import_module("plumb.intake.env")
        assert env_module._venv_is_empty(tmp_path / ".venv") is True

    def test_a_dist_info_directory_makes_a_venv_non_empty(self, tmp_path: Path) -> None:
        env_module = importlib.import_module("plumb.intake.env")
        venv = tmp_path / ".venv"
        site = venv / "lib" / "python3.11" / "site-packages"
        site.mkdir(parents=True)
        assert env_module._venv_is_empty(venv) is True
        (site / "foo-1.0.dist-info").mkdir()
        assert env_module._venv_is_empty(venv) is False


class TestMutations:
    def test_disabling_the_empty_guard_breaks_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_module = importlib.import_module("plumb.intake.env")
        monkeypatch.setattr(env_module.subprocess, "run", _fake_uv_success)
        monkeypatch.setattr(env_module, "_venv_is_empty", lambda venv: False)
        checkout_dir = _checkout_with_venv(tmp_path / "proj", {"poetry.lock": b"# lock\n"}, populated=False)
        checkout = resolve_local(checkout_dir)
        descriptor = _descriptor(checkout)
        with pytest.raises(AssertionError, match="recorded as a build"):
            _assert_the_empty_environment_is_refused(checkout, descriptor)