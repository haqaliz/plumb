"""The public seam: the intake API surface and its named-cause contract (I4).

The `plumb.intake` module is the boundary C3 consumes. This pins what it
exposes — the three resolvers, the descriptor/build seam, the records, and the
causes — so a rename or a dropped export is a test failure rather than a
surprise. The named-cause vocabulary is also pinned here: every cause is a
`RuntimeError` (so it is catchable uniformly) and is documented in the module
docstring with its future `UNVERIFIED` mapping.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import plumb.intake as intake


class TestThePublicApiSurface:
    def test_the_resolvers_and_descriptor_are_exposed(self) -> None:
        for name in (
            "resolve_local",
            "resolve_git",
            "resolve_archive",
            "describe_environment",
            "build_environment",
            "scan_manifests",
            "uv_sync_runner",
            "plumb_tree_hash",
            "git_tree_hash",
        ):
            assert callable(getattr(intake, name)), name

    def test_the_records_are_exposed(self) -> None:
        for name in ("Checkout", "SourceRecord", "TreeHash", "ManifestScan", "EnvDescriptor", "EnvBuild"):
            assert hasattr(intake, name), name

    def test_the_named_causes_are_exposed(self) -> None:
        for name in ("SourceNotFound", "RevNotFound", "UnsupportedArchive", "EnvBuildFailed"):
            assert issubclass(getattr(intake, name), RuntimeError), name


class TestTheNamedCauseVocabulary:
    def test_every_cause_is_a_runtime_error(self) -> None:
        for cause in (
            intake.SourceNotFound,
            intake.RevNotFound,
            intake.UnsupportedArchive,
            intake.EnvBuildFailed,
        ):
            with pytest.raises(cause):
                raise cause("boom")

    def test_the_module_docstring_documents_the_unverified_mapping(self) -> None:
        doc = intake.__doc__ or ""
        for cause in ("SourceNotFound", "RevNotFound", "UnsupportedArchive", "EnvBuildFailed"):
            assert cause in doc, cause
        assert "UNVERIFIED" in doc


class TestSeamSmoke:
    def test_resolve_describe_build_with_a_stub_runner(self, tmp_path: Path) -> None:
        repo = tmp_path / "proj"
        repo.mkdir()
        (repo / "uv.lock").write_bytes(b"version = 1\n")
        (repo / "pyproject.toml").write_bytes(b'[project]\nrequires-python = ">=3.11"\n')
        checkout = intake.resolve_local(repo)
        descriptor = intake.describe_environment(checkout, tool_versions={})
        assert descriptor.policy == "lockfile"

        def stub_runner(checkout, descriptor):
            return intake.EnvBuild(ok=True, policy=descriptor.policy, detail="stub")

        build = intake.build_environment(checkout, descriptor, runner=stub_runner)
        assert build.ok