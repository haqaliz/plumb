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
`BindingInvalid`, `PdfInputError`, `BundleRefused`, `CorpusRefused`) map by type
in `_CAUSE_MAP`; the run package's *recorded* causes (`WONT_RUN`, `TIMEOUT`,
`NO_ARTIFACT`, `STALE_ARTIFACT`) normally flow through verdicts rather than
exceptions, but an exception carrying a `cause` attribute that names one maps
too. `ValueError` from the record readers (`parse_trace`, `parse_claims`) is
`RECORD_INVALID`; anything else is `SPINE_ERROR` — a bug, not a user error, and
never a traceback.

**The seams.** `run_live` and `replay_record` are the dispatch targets of `verify`
(live and `--from-record` modes); `cmd_corpus_bank` is the dispatch target of
`corpus bank`, which banks a verify record into the discrepancy corpus through
the same replay chain `replay_record` reads it by, and `cmd_corpus_report` is the
dispatch target of `corpus report`, which reads the store back and reports
coverage, precision and recall over the banked cases (`plumb.cli.corpus`).
`render_verdicts` is the pure rendering seam the other two compose — it takes a
`VerdictSet` and returns bytes (`plumb.cli.render`), never deciding an exit
code. `run_live` and `replay_record` take the parsed `args`
namespace and return the exit code — the shell trusts the seams' verdict-level
decision, because only the spine can see the verdicts. In the cli-core aspect the
seams were stubs raising `SpineError`; the render aspect replaced `render_verdicts`
without touching the shell, the replay aspect replaced `replay_record`
(`plumb.cli.replay`), and the live aspect replaced the remaining one (`plumb.cli.live`).
The shell guarantees, before dispatch: live mode has a `<paper>` and a
`<repo>` and a `--bindings` file, the paper path is a readable `.md`/`.pdf`, the
repo is a known kind (local directory, git URL with `--rev`, or archive — anything
else is a usage error), a `--out` bundle has an existing signer key, and
`--from-record` carries none of the live-mode arguments.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from plumb.bundle.causes import BundleRefused
from plumb.corpus.causes import CorpusRefused
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
from plumb.cli.corpus import cmd_corpus_bank, cmd_corpus_report
from plumb.cli.render import render_verdicts
from plumb.cli.replay import replay_record
from plumb.verify.causes import ENV_BUILD_FAILED, BindingInvalid

__all__ = [
    "BINDING_INVALID",
    "BUNDLE_REFUSED",
    "CLI_CAUSES",
    "CORPUS_REFUSED",
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
    "cmd_corpus_bank",
    "cmd_corpus_report",
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
CORPUS_REFUSED = "CORPUS_REFUSED"
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
        CORPUS_REFUSED,
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
            "Live runs happen under a per-inputs work area (~/.plumb-runs): the "
            "checkout, the run and its captured objects are named deterministically "
            "from the inputs and replaced on re-run; only the signed bundle (--out) "
            "is evidence.\n\n"
            "Flags:\n"
            "  --rev REV            git revision for a git-URL <repo>\n"
            "  --bindings FILE      JSON bindings file (required in live mode)\n"
            "  --out DIR            write a signed, replayable bundle to DIR\n"
            "  --bank               bank the run's record into the write-once\n"
            "                       discrepancy corpus (default store: corpus/local)\n"
            "  --from-record DIR    replay a committed record instead of running live\n"
            "  --no-env-build       skip the real environment build (offline stub);\n"
            "                       the real uv sync runs only without this flag, at\n"
            "                       dev time on your own compute\n"
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
            "record and takes no <paper>, <repo>, --bindings, --rev or --no-env-build.\n\n"
            "corpus bank <record-dir> [--store DIR] folds a verify record into the "
            "write-once discrepancy corpus; a record that would not replay does not "
            "bank. corpus report [--store DIR] reports coverage, precision and "
            "recall over the banked cases, every figure with its denominator and "
            "its label authority."
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
    verify.add_argument("--bank", action="store_true",
                        help="bank the run's record into the discrepancy corpus "
                             "(default store: corpus/local)")
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
    corpus = subcommands.add_parser(
        "corpus",
        help="bank a verify record into, or report over, the discrepancy corpus",
        description=(
            "Fold a committed verify record into the write-once, content-addressed "
            "discrepancy corpus, or report coverage, precision and recall over the "
            "banked cases. A banked record is re-validated through the replay "
            "chain — its claims re-admitted against its own paper, its verdicts "
            "re-derived from the stored trace and cross-checked against the "
            "committed verdicts.json — and refused with a named cause if it does "
            "not replay. A human-authored labels.json beside the record is "
            "transported into the case, never invented. A report reads every "
            "case back through the store's hash-verified path; a tampered or "
            "unreadable case refuses the whole report."
        ),
    )
    corpus_commands = corpus.add_subparsers(required=True, metavar="SUBCOMMAND")
    bank = corpus_commands.add_parser(
        "bank",
        help="bank <record-dir> as a case",
        description=(
            "Bank the record at <record-dir> under <store-dir>/<case-id>/, "
            "write-once. A re-bank of the identical record is a no-op; a "
            "conflicting re-bank is refused and the existing case is untouched."
        ),
    )
    bank.add_argument("record_dir", metavar="<record-dir>",
                      help="a verify record directory (claims, bindings, trace, "
                           "objects, paper)")
    bank.add_argument("--store", metavar="DIR", default="corpus/local",
                      help="the corpus store directory (default: corpus/local)")
    bank.set_defaults(handler=cmd_corpus_bank)
    report = corpus_commands.add_parser(
        "report",
        help="report coverage, precision and recall over the store",
        description=(
            "Read every <case-id>/ directory under <store-dir>/ that carries a "
            "case.json manifest, and report per case and pooled: coverage "
            "(bound/claims by the C4 bound definition), precision over the "
            "labeled DIVERGEDs (confirmed / confirmed+refuted), and recall over "
            "the labeled claims — every figure with its denominator, and the "
            "label-authority declaration next to each rate. An unlabeled "
            "DIVERGED is in neither side of precision; UNVERIFIED claims are "
            "never bound and never folded into a rate. A tampered or unreadable "
            "case refuses the whole report with a named cause; an empty store "
            "reports zeros."
        ),
    )
    report.add_argument("--store", metavar="DIR", default="corpus/local",
                        help="the corpus store directory (default: corpus/local)")
    report.add_argument("--authority", choices=("owner", "third-party"),
                        default="owner",
                        help="whose labels the report measures (default: owner)")
    report.add_argument("--json", action="store_true",
                        help="emit canonical JSON instead of the report table")
    report.set_defaults(handler=cmd_corpus_report)
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
    kind = repo_kind(args.repo)
    if kind is None:
        parser.error(
            f"<repo> {args.repo!r} is not a local directory, a git URL, or an archive"
        )
    if kind != "git" and args.rev is not None:
        parser.error("--rev applies only to a git-URL <repo>")
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
    (CorpusRefused, CORPUS_REFUSED),
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


from plumb.cli.live import repo_kind, run_live  # noqa: E402  (seam import; no cycle)


if __name__ == "__main__":
    sys.exit(main())