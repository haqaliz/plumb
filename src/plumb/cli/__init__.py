"""The `plumb` CLI shell: argparse, the exit-code contract, and the named-cause contract.

This is the load-bearing surface the render, replay and live-spine aspects plug into
(`docs/planning/verify-cli/cli-core/spec.md`). It is deliberately thin: everything
the spine does lives behind three importable seams, and everything this module owns
is the argument surface, the failure contract, and the dispatch:

**Exit codes.** 0 = every claim decided and the run succeeded; 1 = any `UNVERIFIED`,
any spine failure, any named cause; 2 = usage error (argparse's own stderr message).
`main(argv=None) -> int` never raises — `SystemExit` from argparse (help, usage
errors) is converted to its code, and every other exception is mapped to a named
cause and rendered as `plumb verify: <CAUSE>: <detail>` on stderr.

**The named-cause vocabulary.** Closed, one name per failure class from the PRD's
failure table. The engine's raised exceptions (`SourceNotFound`, `RevNotFound`,
`UnsupportedArchive`, `EnvBuildFailed`, `EntryPointMissing`/`Ambiguous`,
`BindingInvalid`, `PdfInputError`, `BundleRefused`) map by type in `_CAUSE_MAP`; the
run package's *recorded* causes (`WONT_RUN`, `TIMEOUT`, `NO_ARTIFACT`,
`STALE_ARTIFACT`) normally flow through verdicts rather than exceptions, but an
exception carrying a `cause` attribute that names one maps too. `ValueError` from
the record readers (`parse_trace`, `parse_claims`) is `RECORD_INVALID`; anything
else is `SPINE_ERROR` — a bug, not a user error, and never a traceback.

**The seams.** `run_live` and `replay_record` are the dispatch targets of `verify`
(live and `--from-record` modes); `render_verdicts` is the pure rendering seam the
other two compose — it takes a `VerdictSet` and returns bytes (`plumb.cli.render`),
never deciding an exit code. `run_live` and `replay_record` take the parsed `args`
namespace and return the exit code — the shell trusts the seams' verdict-level
decision, because only the spine can see the verdicts. In the cli-core aspect the
seams were stubs raising `SpineError`; the render aspect replaced `render_verdicts`
without touching the shell, and the replay and live aspects replace the remaining two.
The shell guarantees, before dispatch: live mode has a `<paper>` and a
`<repo>` and a `--bindings` file, the paper path is a readable `.md`/`.pdf`, a
`--out` bundle has an existing signer key, and `--from-record` carries none of the
live-mode arguments.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from plumb.bundle.causes import BundleRefused
from plumb.intake.causes import EnvBuildFailed, RevNotFound, SourceNotFound, UnsupportedArchive
from plumb.pdf import PdfInputError
from plumb.run.causes import (
    NO_ARTIFACT,
    STALE_ARTIFACT,
    TIMEOUT,
    WONT_RUN,
    EntryPointAmbiguous,
    EntryPointMissing,
)
from plumb.cli.render import render_verdicts
from plumb.verify.causes import ENV_BUILD_FAILED, BindingInvalid

__all__ = [
    "BINDING_INVALID",
    "BUNDLE_REFUSED",
    "CLI_CAUSES",
    "ENTRYPOINT_AMBIGUOUS",
    "ENTRYPOINT_MISSING",
    "ENV_BUILD_FAILED",
    "KEY_MISSING",
    "NO_ARTIFACT",
    "PAPER_UNREADABLE",
    "RECORD_INVALID",
    "REV_NOT_FOUND",
    "SOURCE_NOT_FOUND",
    "SPINE_ERROR",
    "STALE_ARTIFACT",
    "TIMEOUT",
    "UNSUPPORTED_ARCHIVE",
    "USAGE_ERROR",
    "WONT_RUN",
    "build_parser",
    "cmd_verify",
    "main",
    "replay_record",
    "render_verdicts",
    "run_live",
]

#: The engine's own names pass through unchanged; the rest are this module's.
ENTRYPOINT_MISSING = EntryPointMissing.cause
ENTRYPOINT_AMBIGUOUS = EntryPointAmbiguous.cause

USAGE_ERROR = "USAGE_ERROR"
PAPER_UNREADABLE = "PAPER_UNREADABLE"
SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
REV_NOT_FOUND = "REV_NOT_FOUND"
UNSUPPORTED_ARCHIVE = "UNSUPPORTED_ARCHIVE"
BINDING_INVALID = "BINDING_INVALID"
RECORD_INVALID = "RECORD_INVALID"
KEY_MISSING = "KEY_MISSING"
BUNDLE_REFUSED = "BUNDLE_REFUSED"
SPINE_ERROR = "SPINE_ERROR"

#: The closed CLI vocabulary, from the PRD's failure table.
CLI_CAUSES = frozenset(
    {
        USAGE_ERROR,
        PAPER_UNREADABLE,
        SOURCE_NOT_FOUND,
        REV_NOT_FOUND,
        UNSUPPORTED_ARCHIVE,
        ENV_BUILD_FAILED,
        ENTRYPOINT_MISSING,
        ENTRYPOINT_AMBIGUOUS,
        WONT_RUN,
        TIMEOUT,
        NO_ARTIFACT,
        STALE_ARTIFACT,
        BINDING_INVALID,
        RECORD_INVALID,
        KEY_MISSING,
        BUNDLE_REFUSED,
        SPINE_ERROR,
    }
)

#: The default signer key, `principal plumb-bundle` (PRD requirement 5).
DEFAULT_SIGNER_KEY = "~/.ssh/plumb_bundle_ed25519"

_PAPER_KINDS = (".md", ".pdf")


class SpineError(RuntimeError):
    """A spine path that is not built, or an unexpected internal failure."""


class PaperUnreadable(RuntimeError):
    """The `<paper>` path is missing, unreadable, or not a .md/.pdf paper."""


class KeyMissing(RuntimeError):
    """`--out` was given and no signer key exists at the chosen path."""


def build_parser() -> argparse.ArgumentParser:
    """The full argument surface: one subcommand, `verify`, with the PRD flag set."""
    parser = argparse.ArgumentParser(
        prog="plumb",
        description=(
            "plumb verify <paper> <repo>: re-derive a paper's quantitative claims "
            "from its own code and data, and decide each claim against the value the "
            "run actually produced. <paper> is a .md or .pdf path; <repo> is a local "
            "directory, an https git URL (with --rev), or an archive path.\n\n"
            "Flags:\n"
            "  --rev REV            git revision for a git-URL <repo>\n"
            "  --bindings FILE      JSON bindings file (required in live mode)\n"
            "  --out DIR            write a signed, replayable bundle to DIR\n"
            "  --from-record DIR    replay a committed record instead of running live\n"
            "  --no-env-build       skip the real environment build (offline stub)\n"
            "  --signer-key PATH    SSH private key for bundle signing\n"
            "                       (default: ~/.ssh/plumb_bundle_ed25519)\n"
            "  --no-paper           omit the paper from the bundle\n"
            "  --json               emit canonical JSON instead of the verdict table"
        ),
        epilog=(
            "Exit codes:\n"
            "  0  every claim decided and the run succeeded\n"
            "  1  any UNVERIFIED verdict, spine failure, or named cause\n"
            "  2  usage error\n\n"
            "--bindings FILE is required in live mode; --from-record carries its own "
            "record and takes no <paper>, <repo>, --bindings, --rev or --no-env-build."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subcommands = parser.add_subparsers(required=True, metavar="COMMAND")
    verify = subcommands.add_parser(
        "verify",
        help="verify a paper's claims against its own code's run",
        description=(
            "Re-derive the paper's quantitative claims from its own artifacts and "
            "decide each one. Live mode (the default) runs the spine end-to-end; "
            "--from-record replays a committed record instead. --bindings FILE is "
            "required in live mode."
        ),
    )
    verify.add_argument("paper", nargs="?", metavar="<paper>",
                        help="the paper: a readable .md or .pdf path")
    verify.add_argument("repo", nargs="?", metavar="<repo>",
                        help="the code: a local directory, an https git URL, or an archive")
    verify.add_argument("--rev", metavar="REV",
                        help="git revision for a git-URL <repo>")
    verify.add_argument("--bindings", metavar="FILE",
                        help="JSON bindings file (required in live mode)")
    verify.add_argument("--out", metavar="DIR",
                        help="write a signed, replayable bundle to DIR")
    verify.add_argument("--from-record", metavar="DIR",
                        help="replay a committed record instead of running live")
    verify.add_argument("--no-env-build", action="store_true",
                        help="skip the real environment build (offline stub)")
    verify.add_argument("--signer-key", metavar="PATH",
                        help="SSH private key for bundle signing (default: "
                             "~/.ssh/plumb_bundle_ed25519)")
    verify.add_argument("--no-paper", action="store_true",
                        help="omit the paper from the bundle")
    verify.add_argument("--json", action="store_true",
                        help="emit canonical JSON instead of the verdict table")
    verify.set_defaults(handler=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse and dispatch; never raises. Returns 0, 1 or 2 (see module docstring)."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.handler(args, parser)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 0
    except Exception as exc:
        cause, detail = _map_cause(exc)
        print(f"plumb verify: {cause}: {detail}", file=sys.stderr)
        return 1


def cmd_verify(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Validate the argument combination, then dispatch to the record or live seam."""
    if args.from_record is not None:
        if any(
            (
                args.paper is not None,
                args.repo is not None,
                args.bindings is not None,
                args.rev is not None,
                args.no_env_build,
            )
        ):
            parser.error(
                "--from-record replays a record and cannot be combined with <paper>, "
                "<repo>, --bindings, --rev or --no-env-build"
            )
        if args.out is not None:
            _check_signer_key(args.signer_key)
        return replay_record(args)

    if args.paper is None or args.repo is None:
        parser.error("the following arguments are required: paper, repo")
    if args.bindings is None:
        parser.error("--bindings FILE is required in live mode (see --help)")
    _check_paper(args.paper)
    if args.out is not None:
        _check_signer_key(args.signer_key)
    return run_live(args)


def _check_paper(paper: str) -> None:
    path = Path(paper)
    if not path.is_file():
        raise PaperUnreadable(f"{paper} is not a readable file")
    if path.suffix.lower() not in _PAPER_KINDS:
        raise PaperUnreadable(f"{paper} is not a .md or .pdf paper")


def _check_signer_key(signer_key: str | None) -> None:
    path = Path(signer_key).expanduser() if signer_key else Path(DEFAULT_SIGNER_KEY).expanduser()
    if not path.is_file():
        raise KeyMissing(
            f"no signer key at {path} (--signer-key PATH, default "
            f"{DEFAULT_SIGNER_KEY})"
        )


#: Engine exceptions to their CLI cause, first match wins.
_CAUSE_MAP: tuple[tuple[type[Exception], str], ...] = (
    (SourceNotFound, SOURCE_NOT_FOUND),
    (RevNotFound, REV_NOT_FOUND),
    (UnsupportedArchive, UNSUPPORTED_ARCHIVE),
    (EnvBuildFailed, ENV_BUILD_FAILED),
    (EntryPointMissing, ENTRYPOINT_MISSING),
    (EntryPointAmbiguous, ENTRYPOINT_AMBIGUOUS),
    (BindingInvalid, BINDING_INVALID),
    (PdfInputError, PAPER_UNREADABLE),
    (BundleRefused, BUNDLE_REFUSED),
    (PaperUnreadable, PAPER_UNREADABLE),
    (KeyMissing, KEY_MISSING),
    (SpineError, SPINE_ERROR),
)


def _map_cause(exc: Exception) -> tuple[str, str]:
    """The `(cause, detail)` pair for `exc`; never raises, never re-raises."""
    for exc_type, cause in _CAUSE_MAP:
        if isinstance(exc, exc_type):
            return cause, str(exc)
    carried = getattr(exc, "cause", None)
    if isinstance(carried, str) and carried in CLI_CAUSES:
        return carried, str(exc)
    if isinstance(exc, ValueError):
        return RECORD_INVALID, str(exc)
    return SPINE_ERROR, str(exc)


def run_live(args: argparse.Namespace) -> int:
    """Live spine seam: intake -> run -> verify -> render (implemented by a later aspect).

    The shell has already validated the paper path, the bindings flag and the signer
    key. Raises the engine's named exceptions on failure; returns the exit code (0,
    or 1 when any claim is `UNVERIFIED`).
    """
    raise SpineError("the live spine is not implemented yet (run_live)")


def replay_record(args: argparse.Namespace) -> int:
    """Record replay seam: re-derive verdicts from a committed record, then render.

    The shell has already rejected the live-mode arguments. An unreadable record is
    reported by raising `ValueError` (as `parse_trace` and `parse_claims` do),
    which the failure contract renders as `RECORD_INVALID`.
    """
    raise SpineError("record replay is not implemented yet (replay_record)")


if __name__ == "__main__":
    sys.exit(main())