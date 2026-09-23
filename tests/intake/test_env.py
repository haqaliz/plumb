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

from pathlib import Path

import pytest

from plumb.intake.causes import EnvBuildFailed
from plumb.intake.checkout import resolve_local
from plumb.intake.env import (
    _DEFAULT_PYTHON_PIN,
    EnvBuild,
    build_environment,
    describe_environment,
)
from plumb.intake.manifest import scan_manifests


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

    def test_reports_absence_as_none(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(tmp_path / "empty", {"notes.md": b"hi"})
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.uv_lock is None
        assert scan.pyproject is None
        assert scan.requirements == ()
        assert scan.environment_yml is None
        assert scan.makefile is None
        assert scan.main_py is None

    def test_does_not_look_inside_subdirectories(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj", {"sub/pyproject.toml": b"[project]\n", "sub/uv.lock": b""}
        )
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.pyproject is None
        assert scan.uv_lock is None

    def test_requirements_globs_only_at_the_root(self, tmp_path: Path) -> None:
        checkout_dir = make_checkout(
            tmp_path / "proj",
            {"requirements.txt": b"", "sub/requirements.txt": b"", "requirements-prod.txt": b""},
        )
        scan = scan_manifests(resolve_local(checkout_dir))
        assert scan.requirements == (Path("requirements-prod.txt"), Path("requirements.txt"))


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