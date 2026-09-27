"""cli-core: the shell, the exit-code contract, and the named-cause contract.

The CLI is the load-bearing contract the render, replay and live-spine aspects plug
into, so this file pins the shell itself: the `[project.scripts]` entry point, the
`main(argv=None) -> int` surface, the 0/1/2 exit-code contract, and the named-cause
vocabulary from the PRD's failure table. Every acceptance criterion of the aspect
spec (`docs/planning/verify-cli/cli-core/spec.md`) is one test class here.

Two shapes of test, per the plan: the entry-point-facing paths (`--help`, usage
errors) run `uv run plumb` as a subprocess — `subprocess` is deliberately outside
`conftest.py`'s in-process network blocker (`tests/conftest.py:14-17`), and the
child is a fresh interpreter with no sockets of its own — and everything else
drives `main(argv=...)` in-process with the seams monkeypatched. The seams are
real (`run_live` in `plumb.cli.live`, `replay_record` in `plumb.cli.replay`);
a test that needs a later aspect's trigger replaces the seam with one that
raises the engine exception, which is exactly what the aspect's own path does.
The live-mode tests pass an existing directory as `<repo>` — the shell validates
the repo kind before dispatch — and a `--bindings` file whose existence the
seam, not the shell, checks.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

import pytest

from plumb.bundle.causes import BundleRefused
from plumb.cli import (
    BINDING_INVALID,
    BUNDLE_REFUSED,
    CLI_CAUSES,
    ENTRYPOINT_AMBIGUOUS,
    ENTRYPOINT_MISSING,
    ENV_BUILD_FAILED,
    KEY_MISSING,
    NO_ARTIFACT,
    PAPER_UNREADABLE,
    RECORD_INVALID,
    REV_NOT_FOUND,
    SOURCE_NOT_FOUND,
    SPINE_ERROR,
    STALE_ARTIFACT,
    TIMEOUT,
    UNSUPPORTED_ARCHIVE,
    USAGE_ERROR,
    WONT_RUN,
    SpineError,
    main,
    _map_cause,
)
from plumb.intake.causes import (
    EnvBuildFailed,
    RevNotFound,
    SourceNotFound,
    UnsupportedArchive,
)
from plumb.pdf import PdfInputError
from plumb.run.causes import EntryPointAmbiguous, EntryPointMissing
from plumb.verify.causes import BindingInvalid

_REPO_ROOT = Path(__file__).parents[1]

FLAGS = (
    "--rev",
    "--bindings",
    "--out",
    "--from-record",
    "--no-env-build",
    "--signer-key",
    "--no-paper",
    "--json",
)


def run_cli(*argv: str) -> subprocess.CompletedProcess[str]:
    """Run the real `plumb` console script in a fresh interpreter, from the repo root."""
    return subprocess.run(
        ["uv", "run", "plumb", *argv],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


class _CausedError(RuntimeError):
    """An exception carrying a recorded run cause, as the run package records them."""

    def __init__(self, cause: str, detail: str) -> None:
        super().__init__(detail)
        self.cause = cause


def _raising(exc: Exception):
    def _raise(args) -> int:
        raise exc

    return _raise


@pytest.fixture
def paper(tmp_path: Path) -> Path:
    path = tmp_path / "paper.md"
    path.write_text("# Title\n\nA reported value of 0.87.\n", encoding="utf-8")
    return path


@pytest.fixture
def bindings(tmp_path: Path) -> Path:
    path = tmp_path / "bindings.json"
    path.write_text('{"bindings": []}\n', encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """An existing directory: the shell's repo-kind check must let it through."""
    path = tmp_path / "proj"
    path.mkdir()
    return path


class TestHelpDocumentsTheContract:
    """Acceptance 1: `uv run plumb --help` exits 0 and documents the contract."""

    def test_help_exits_zero_and_documents_everything(self) -> None:
        result = run_cli("--help")
        assert result.returncode == 0
        out = result.stdout
        assert "verify" in out
        for flag in FLAGS:
            assert flag in out
        assert "Exit codes" in out
        assert "usage error" in out
        assert "UNVERIFIED" in out
        assert "required in live mode" in out

    def test_help_output_is_byte_identical_across_invocations(self, capsys) -> None:
        """Acceptance 6: the determinism floor for help text, in-process."""
        assert main(["--help"]) == 0
        first = capsys.readouterr().out
        assert main(["--help"]) == 0
        second = capsys.readouterr().out
        assert first == second

    def test_verify_help_documents_the_flags(self) -> None:
        result = run_cli("verify", "--help")
        assert result.returncode == 0
        for flag in FLAGS:
            assert flag in result.stdout


class TestUsageErrorsExitTwo:
    """Acceptance 2: usage errors are argparse's own message on stderr, exit 2."""

    def test_verify_without_args_names_the_missing_positionals(self) -> None:
        result = run_cli("verify")
        assert result.returncode == 2
        assert "paper" in result.stderr
        assert "repo" in result.stderr
        assert result.stdout == ""

    def test_no_subcommand_is_a_usage_error(self) -> None:
        result = run_cli()
        assert result.returncode == 2
        assert result.stdout == ""

    def test_unknown_flag_is_a_usage_error(self) -> None:
        result = run_cli("verify", "--bogus")
        assert result.returncode == 2
        assert "bogus" in result.stderr
        assert result.stdout == ""

    def test_live_mode_without_bindings_is_a_usage_error(
        self, paper: Path, capsys
    ) -> None:
        code = main(["verify", str(paper), "some-repo"])
        assert code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "--bindings" in captured.err

    @pytest.mark.parametrize(
        "extra",
        [
            ("paper.md",),
            ("paper.md", "repo2"),
            ("--bindings", "b.json"),
            ("--rev", "v1"),
            ("--no-env-build",),
        ],
        ids=("paper", "paper-repo", "bindings", "rev", "no-env-build"),
    )
    def test_from_record_rejects_live_arguments(
        self, capsys, extra: tuple[str, ...]
    ) -> None:
        argv = ["verify", "--from-record", "some-record", *extra]
        code = main(argv)
        assert code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "--from-record" in captured.err

    def test_from_record_alone_dispatches_to_replay(self, capsys) -> None:
        """Replay mode is a valid invocation: the real seam reports the record, exit 1."""
        assert main(["verify", "--from-record", "some-record"]) == 1
        captured = capsys.readouterr()
        assert captured.err.startswith(f"plumb verify: {RECORD_INVALID}: ")

    def test_live_mode_without_paper_or_repo_names_them(self, capsys) -> None:
        code = main(["verify", "--bindings", "b.json"])
        assert code == 2
        captured = capsys.readouterr()
        assert "paper" in captured.err
        assert "repo" in captured.err


class TestEveryNamedCauseIsEmitted:
    """Acceptance 3: every cause in the PRD failure table is emitted."""

    def test_vocabulary_is_closed_and_pass_through_unchanged(self) -> None:
        from plumb import cli
        from plumb.run.causes import (
            NO_ARTIFACT as RUN_NO_ARTIFACT,
            STALE_ARTIFACT as RUN_STALE_ARTIFACT,
            TIMEOUT as RUN_TIMEOUT,
            WONT_RUN as RUN_WONT_RUN,
        )
        from plumb.verify.causes import ENV_BUILD_FAILED as VERIFY_ENV_BUILD_FAILED

        expected = {
            USAGE_ERROR, PAPER_UNREADABLE, SOURCE_NOT_FOUND, REV_NOT_FOUND,
            UNSUPPORTED_ARCHIVE, ENV_BUILD_FAILED, ENTRYPOINT_MISSING,
            ENTRYPOINT_AMBIGUOUS, WONT_RUN, TIMEOUT, NO_ARTIFACT, STALE_ARTIFACT,
            BINDING_INVALID, RECORD_INVALID, KEY_MISSING, BUNDLE_REFUSED, SPINE_ERROR,
        }
        assert CLI_CAUSES == expected
        assert cli.WONT_RUN is RUN_WONT_RUN
        assert cli.TIMEOUT is RUN_TIMEOUT
        assert cli.NO_ARTIFACT is RUN_NO_ARTIFACT
        assert cli.STALE_ARTIFACT is RUN_STALE_ARTIFACT
        assert cli.ENV_BUILD_FAILED is VERIFY_ENV_BUILD_FAILED

    def test_usage_error_is_usage(self) -> None:
        """`USAGE_ERROR` names the usage class; usage renders as argparse's, exit 2."""
        assert USAGE_ERROR in CLI_CAUSES
        assert run_cli("verify").returncode == 2

    def test_paper_unreadable_through_the_dispatcher(self, capsys) -> None:
        code = main(["verify", "missing.md", "repo", "--bindings", "b.json"])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {PAPER_UNREADABLE}: ")

    @pytest.mark.parametrize(
        "paper_arg", ["missing.md", "paper.txt", "not-a-file"], ids=("missing", "kind", "dir")
    )
    def test_unreadable_paper_kinds(
        self, tmp_path: Path, capsys, paper_arg: str
    ) -> None:
        target = tmp_path / paper_arg
        if paper_arg == "kind":
            target.write_text("x", encoding="utf-8")
        elif paper_arg == "dir":
            target.mkdir()
        code = main(
            ["verify", str(target), "repo", "--bindings", str(tmp_path / "b.json")]
        )
        assert code == 1
        captured = capsys.readouterr()
        assert captured.err.startswith(f"plumb verify: {PAPER_UNREADABLE}: ")

    def test_key_missing_through_the_dispatcher(
        self, paper: Path, tmp_path: Path, capsys
    ) -> None:
        missing = tmp_path / "no-such-key"
        code = main(
            ["verify", str(paper), "repo", "--bindings", "b.json",
             "--out", str(tmp_path / "bundle"), "--signer-key", str(missing)]
        )
        assert code == 1
        captured = capsys.readouterr()
        assert captured.err.startswith(f"plumb verify: {KEY_MISSING}: ")

    @pytest.mark.parametrize(
        ("cause", "exc"),
        [
            (SOURCE_NOT_FOUND, SourceNotFound("no such source")),
            (REV_NOT_FOUND, RevNotFound("no such revision")),
            (UNSUPPORTED_ARCHIVE, UnsupportedArchive("not an archive")),
            (ENV_BUILD_FAILED, EnvBuildFailed("uv sync failed")),
            (ENTRYPOINT_MISSING, EntryPointMissing("no entry point")),
            (ENTRYPOINT_AMBIGUOUS, EntryPointAmbiguous("two entry points")),
            (BINDING_INVALID, BindingInvalid("bindings file refused")),
            (BUNDLE_REFUSED, BundleRefused("bundle would not verify")),
        ],
        ids=(
            "source-not-found", "rev-not-found", "unsupported-archive",
            "env-build-failed", "entrypoint-missing", "entrypoint-ambiguous",
            "binding-invalid", "bundle-refused",
        ),
    )
    def test_engine_exceptions_through_the_dispatcher(
        self, paper: Path, repo: Path, monkeypatch, capsys, cause: str, exc: Exception
    ) -> None:
        monkeypatch.setattr("plumb.cli.run_live", _raising(exc))
        code = main(["verify", str(paper), str(repo), "--bindings", "b.json"])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith(f"plumb verify: {cause}: ")

    @pytest.mark.parametrize(
        "cause",
        [WONT_RUN, TIMEOUT, NO_ARTIFACT, STALE_ARTIFACT],
        ids=("wont-run", "timeout", "no-artifact", "stale-artifact"),
    )
    def test_recorded_run_causes_through_the_dispatcher(
        self, paper: Path, repo: Path, monkeypatch, capsys, cause: str
    ) -> None:
        monkeypatch.setattr("plumb.cli.run_live", _raising(_CausedError(cause, "detail")))
        code = main(["verify", str(paper), str(repo), "--bindings", "b.json"])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.err.startswith(f"plumb verify: {cause}: detail")

    def test_record_invalid_through_the_dispatcher(
        self, monkeypatch, capsys
    ) -> None:
        monkeypatch.setattr(
            "plumb.cli.replay_record",
            _raising(ValueError("not a serialized RunTrace: ...")),
        )
        code = main(["verify", "--from-record", "some-record"])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.err.startswith(f"plumb verify: {RECORD_INVALID}: ")

    def test_an_unexpected_spine_failure_is_still_spine_error(
        self, paper: Path, repo: Path, monkeypatch, capsys
    ) -> None:
        """SPINE_ERROR names a harness bug; the live seam is real now, not a stub."""
        monkeypatch.setattr("plumb.cli.run_live", _raising(RuntimeError("a harness bug")))
        code = main(["verify", str(paper), str(repo), "--bindings", "b.json"])
        assert code == 1
        captured = capsys.readouterr()
        assert captured.err.startswith(f"plumb verify: {SPINE_ERROR}: ")

    def test_pdf_input_error_maps_to_paper_unreadable(self) -> None:
        cause, _ = _map_cause(PdfInputError("cannot read the PDF"))
        assert cause == PAPER_UNREADABLE

    def test_any_unknown_exception_is_a_spine_error(self, capsys) -> None:
        cause, _ = _map_cause(RuntimeError("a harness bug"))
        assert cause == SPINE_ERROR


class TestExitCodeContract:
    """Acceptance 4: `main(argv=...)` returns the documented codes, never raises."""

    def test_main_never_raises_on_any_failure_path(self, capsys) -> None:
        cases = [
            [],
            ["verify"],
            ["verify", "--bogus"],
            ["verify", "missing.md", "repo", "--bindings", "b.json"],
            ["verify", "--from-record", "r", "paper", "repo"],
        ]
        for argv in cases:
            code = main(argv)
            assert isinstance(code, int)

    def test_help_returns_zero(self, capsys) -> None:
        assert main(["--help"]) == 0

    def test_usage_returns_two(self, capsys) -> None:
        assert main([]) == 2
        assert main(["verify"]) == 2
        assert main(["verify", "--bogus"]) == 2

    def test_named_causes_return_one(self, paper: Path, capsys) -> None:
        assert main(["verify", "missing.md", "repo", "--bindings", "b.json"]) == 1

    def test_mapping_layer_maps_every_engine_exception_without_reraise(self) -> None:
        cases = [
            (SourceNotFound("no such source"), SOURCE_NOT_FOUND),
            (RevNotFound("no such revision"), REV_NOT_FOUND),
            (UnsupportedArchive("not an archive"), UNSUPPORTED_ARCHIVE),
            (EnvBuildFailed("uv sync failed"), ENV_BUILD_FAILED),
            (EntryPointMissing("no entry point"), ENTRYPOINT_MISSING),
            (EntryPointAmbiguous("two entry points"), ENTRYPOINT_AMBIGUOUS),
            (BindingInvalid("bindings file refused"), BINDING_INVALID),
            (PdfInputError("cannot read the PDF"), PAPER_UNREADABLE),
            (BundleRefused("bundle would not verify"), BUNDLE_REFUSED),
        ]
        for exc, cause in cases:
            mapped_cause, detail = _map_cause(exc)
            assert mapped_cause == cause
            assert detail == str(exc)


class TestFailureRendering:
    """Acceptance 5: no traceback on stdout; stderr lines carry the cause prefix."""

    _PREFIX = re.compile(r"^plumb verify: [A-Z_]+: ")

    def _assert_cause_rendering(self, captured) -> None:
        assert captured.out == ""
        lines = [line for line in captured.err.splitlines() if line]
        assert lines, "expected a rendered cause on stderr"
        for line in lines:
            assert self._PREFIX.match(line), f"bad cause line: {line!r}"

    def test_engine_cause_lines(self, paper: Path, repo: Path, monkeypatch, capsys) -> None:
        monkeypatch.setattr("plumb.cli.run_live", _raising(SourceNotFound("gone")))
        main(["verify", str(paper), str(repo), "--bindings", "b.json"])
        self._assert_cause_rendering(capsys.readouterr())

    def test_paper_cause_lines(self, capsys) -> None:
        main(["verify", "missing.md", "repo", "--bindings", "b.json"])
        self._assert_cause_rendering(capsys.readouterr())

    def test_key_cause_lines(
        self, paper: Path, tmp_path: Path, capsys
    ) -> None:
        main(
            ["verify", str(paper), "repo", "--bindings", "b.json",
             "--out", str(tmp_path / "bundle"), "--signer-key", str(tmp_path / "nokey")]
        )
        self._assert_cause_rendering(capsys.readouterr())

    def test_spine_cause_lines(self, paper: Path, repo: Path, monkeypatch, capsys) -> None:
        monkeypatch.setattr("plumb.cli.run_live", _raising(SpineError("a harness bug")))
        main(["verify", str(paper), str(repo), "--bindings", "b.json"])
        self._assert_cause_rendering(capsys.readouterr())

    def test_usage_errors_print_no_stdout(self, capsys) -> None:
        main(["verify", "--bogus"])
        assert capsys.readouterr().out == ""