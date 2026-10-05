"""The live spine: `plumb verify <paper> <repo>` end to end (verify-cli live-spine).

`run_live(args)` is the seam the shell dispatches to when `<paper>` and `<repo>`
are given: extract the paper's claims, resolve and pin the repo, describe (and
optionally build) the environment, run the entry point in a deterministic run
area, bind and decide, render the shared table or `--json`, and — for `--out` —
write and self-verify the signed bundle. Everything is on the user's compute;
nothing here reaches a network the user did not authorize.

**The run area is the CLI's own cache, keyed by inputs.** `WORK_ROOT` defaults
to `~/.plumb-runs` (documented in `--help`); the checkout (git/archive sources),
the run directory and its captured objects all live there, named
deterministically from the inputs (`run-<tree-digest12>-<argv-hash8>`), and a
re-run replaces the previous run's slot rather than piling up. The trace never
records these paths (`run/trace.py`), so no rendering can leak them.

**Pre-run failures are the shell's.** An unreadable paper, an unresolvable
repo, a refused bindings file, a failed real env build — all raise the engine's
named exceptions, which `plumb.cli.main` renders as one `plumb verify: CAUSE:
detail` line on stderr with exit 1. **Run-level failures are the table's.**
`EntryPointMissing`/`EntryPointAmbiguous` are folded into `NoRun.from_exception`
so every claim is `UNVERIFIED` with that cause — the run-level cause governs,
and no harness failure can become `DIVERGED` through the CLI. The same cause
line also goes to stderr, and the exit code is the verdict-level contract: 0 iff
every claim is decided.

**The env build is a stub in `--no-env-build` mode.** The offline path
constructs `EnvBuild(ok=True, policy="best-effort", detail="stub")` directly —
`build_environment` without a runner raises `EnvBuildFailed`, so the stub never
goes through it. Without the flag, the real `uv sync` runs through
`uv_sync_runner`, dev-time only; tests always stub.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

from plumb.bundle import SshSigner, build_bundle, verify_bundle
from plumb.bundle.causes import BundleRefused
from plumb.cli.corpus import bank_for_verify
from plumb.cli.record import write_record
from plumb.cli.render import render_verdicts
from plumb.extract.pipeline import extract_claims
from plumb.intake.checkout import resolve_archive, resolve_git, resolve_local
from plumb.intake.env import EnvBuild, build_environment, describe_environment, uv_sync_runner
from plumb.pdf import PdfInputError, pdf_to_markdown
from plumb.run import run_and_capture
from plumb.run.causes import NO_ARTIFACT, EntryPointAmbiguous, EntryPointMissing
from plumb.run.entrypoint import resolve_entrypoint
from plumb.verify import (
    UNVERIFIED,
    BindingInvalid,
    Completed,
    NoRun,
    load_bindings,
    verify_claims,
)

__all__ = ["WORK_ROOT", "derive_run_dir", "repo_kind", "run_live"]

#: The CLI's work area: checkouts, runs and captured objects, keyed by inputs.
WORK_ROOT = Path.home() / ".plumb-runs"

#: The signer identity, as `replay.py` and `tools/bundle_build.py` use it.
_PRINCIPAL = "plumb-bundle"

_JSON = {"sort_keys": True, "ensure_ascii": False, "separators": (",", ":")}

#: The default timeout, matching the isolation posture C2 records.
_TIMEOUT_SECONDS = 1800


def repo_kind(repo: str) -> str | None:
    """`"local"` | `"git"` | `"archive"` for a `<repo>` argument, else `None`.

    An existing directory is local; a `://` or `git@` prefix is a git URL; a
    `.tar.gz`/`.tgz`/`.zip` suffix is an archive. Anything else that looks like
    a path (contains a separator) still resolves as local — so a missing path
    fails with the named `SOURCE_NOT_FOUND`, not a usage error — and a bare
    non-path token is `None`: the shell's usage error (exit 2).
    """
    if Path(repo).is_dir():
        return "local"
    if "://" in repo or repo.startswith("git@"):
        return "git"
    if repo.lower().endswith((".tar.gz", ".tgz", ".zip")):
        return "archive"
    if "/" in repo or "\\" in repo:
        return "local"
    return None


def derive_run_dir(work_root: Path | str, tree_hash, argv) -> Path:
    """The deterministic run area for `(tree, argv)`: `run-<tree12>-<argv8>`.

    `argv_hash` is sha256 over the resolved argv (the same argv the trace
    records), so the name is a pure function of the inputs — never wall clock,
    never a counter — and a re-run of the same inputs reuses the same slot.
    """
    argv_hash = hashlib.sha256(json.dumps(list(argv), **_JSON).encode("utf-8")).hexdigest()
    return Path(work_root) / f"run-{tree_hash.digest[:12]}-{argv_hash[:8]}"


def run_live(args: argparse.Namespace) -> int:
    """The live spine seam: extract -> resolve -> env -> run -> bind -> render -> bank.

    The shell has already validated the paper, the bindings flag, the signer
    key and the repo kind. Raises the engine's named exceptions for pre-run
    failures; returns 0 iff every claim is decided and (with `--bank`) the
    bank succeeded, 1 otherwise. A run-level cause (no entry point, a failed
    or silent run) also prints its named cause line on stderr — the table
    carries the verdicts, the cause line the reason. With `--bank`, the
    record is written into a transient directory that outlives the bank call
    only: the case in the store is the durable artifact.
    """
    if args.bank:
        with tempfile.TemporaryDirectory(prefix="plumb-record-") as tmp:
            return _run_live(args, Path(tmp) / "record")
    return _run_live(args, None)


def _run_live(args: argparse.Namespace, record_dir: Path | None) -> int:
    """Render the verdicts, then (with `--bank`) write and bank the record.

    The record is written only after the verdicts are on stdout, so no
    record-side I/O failure — and no bank refusal — can suppress the verdict
    table; the failure still decides the exit code (1) with a named cause line.
    """
    verdicts, run_failure, materials = _spine(args, record_dir=record_dir)
    sys.stdout.buffer.write(render_verdicts(verdicts, json=args.json))
    sys.stdout.buffer.flush()
    if run_failure is not None:
        cause, detail = run_failure
        print(f"plumb verify: {cause}: {detail}", file=sys.stderr)
    banked = True
    if materials is not None:
        try:
            record = write_record(**materials)
        except OSError as exc:
            banked = False
            print(f"plumb verify: SPINE_ERROR: could not write the record: {exc}", file=sys.stderr)
        else:
            banked = bank_for_verify(record)
    decided = all(v.verdict != UNVERIFIED for v in verdicts.verdicts)
    return 0 if decided and banked else 1


def _spine(args: argparse.Namespace, record_dir: Path | None = None):
    """The ordered spine; returns `(VerdictSet, run-level (cause, detail) | None, materials)`.

    `materials` is `None`, or the `write_record` keyword arguments (including
    `record_dir`) the caller uses to write the record **after rendering** when
    `--bank` was given and the run happened — a run that never started has no
    trace to bank.
    """
    paper_bytes, paper_format, paper_text = _read_paper(Path(args.paper))
    claims, _ = extract_claims(paper_text)
    bindings_bytes = _read_bindings(args.bindings)
    bindings = load_bindings(bindings_bytes, [c.id for c in claims])

    kind = repo_kind(args.repo)
    if kind is None:  # unreachable via cmd_verify, which rejects the kind first
        from plumb.cli import SpineError

        raise SpineError(f"<repo> {args.repo!r} has no resolvable kind")
    checkout = _resolve(kind, args.repo, args.rev)
    descriptor = describe_environment(checkout)
    env_build = _env_build(args, checkout, descriptor)

    try:
        entrypoint = resolve_entrypoint(checkout, descriptor.manifests)
    except (EntryPointMissing, EntryPointAmbiguous) as exc:
        verdicts = verify_claims(claims, bindings, NoRun.from_exception(exc))
        return verdicts, (exc.cause, str(exc)), None

    run_dir = derive_run_dir(WORK_ROOT, checkout.tree_hash, entrypoint.argv)
    _reset(run_dir)
    trace, capture = run_and_capture(
        checkout, env_build, entrypoint, run_dir=run_dir, timeout_seconds=_TIMEOUT_SECONDS,
    )
    verdicts = verify_claims(claims, bindings, Completed(trace, capture))
    if args.out is not None:
        _build_bundle(args, paper_bytes, paper_format, Path(args.paper), claims,
                      bindings_bytes=bindings_bytes, trace=trace, capture=capture,
                      environment=descriptor.to_text(), checkout=checkout)
    record = None
    if record_dir is not None:
        record = dict(
            record_dir=record_dir, claims=claims, bindings_bytes=bindings_bytes, trace=trace,
            capture=capture, paper_bytes=paper_bytes, paper_format=paper_format,
        )
    return verdicts, _trace_failure(trace), record


# -----------------------------------------------------------------------------
# Inputs
# -----------------------------------------------------------------------------


def _read_paper(path: Path) -> tuple[bytes, str, str]:
    """The paper as (raw bytes, "pdf" | "markdown", text); unreadable -> named cause."""
    from plumb.cli import PaperUnreadable

    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PaperUnreadable(f"{path} is not readable: {exc}") from exc
    if path.suffix.lower() == ".pdf":
        try:
            return data, "pdf", pdf_to_markdown(data)
        except PdfInputError as exc:
            raise PaperUnreadable(f"{path} is not a readable PDF: {exc}") from exc
    try:
        return data, "markdown", data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PaperUnreadable(f"{path} is not UTF-8 markdown: {exc}") from exc


def _read_bindings(path: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise BindingInvalid(f"no bindings file at {path}: {exc}") from exc


# -----------------------------------------------------------------------------
# Repo and environment
# -----------------------------------------------------------------------------


def _resolve(kind: str, repo: str, rev: str | None):
    """Resolve `repo` by its kind; git/archive checkouts live under the work root."""
    if kind == "local":
        return resolve_local(repo)
    checkout_dir = WORK_ROOT / ("checkout-" + hashlib.sha256(repo.encode()).hexdigest()[:16])
    _reset(checkout_dir)
    if kind == "git":
        return resolve_git(repo, rev, checkout_dir=checkout_dir)
    return resolve_archive(repo, checkout_dir=checkout_dir)


def _env_build(args: argparse.Namespace, checkout, descriptor) -> EnvBuild:
    """The stub for `--no-env-build`; the real `uv sync` only without it."""
    if args.no_env_build:
        return EnvBuild(ok=True, policy="best-effort", detail="stub")
    return build_environment(checkout, descriptor, runner=uv_sync_runner)


def _reset(path: Path) -> None:
    """Clear a work-area slot so a deterministic name can be run again."""
    if path.exists():
        shutil.rmtree(path)


def _trace_failure(trace) -> tuple[str, str] | None:
    """The run-level (cause, detail) a completed run records, if any."""
    if trace.failure is not None:
        return trace.failure.cause, trace.failure.detail
    if NO_ARTIFACT in trace.causes:
        return NO_ARTIFACT, "the run succeeded but wrote no capturable output"
    return None


# -----------------------------------------------------------------------------
# Bundle
# -----------------------------------------------------------------------------


def _build_bundle(args: argparse.Namespace, paper: bytes, paper_format: str,
                  paper_path: Path, claims, *, bindings_bytes: bytes, trace, capture,
                  environment: str, checkout) -> Path:
    """The signed bundle, then verified under its own key (refused otherwise)."""
    key = _signer_key(args.signer_key)
    out = build_bundle(
        Path(args.out), claims=claims, paper=paper, paper_format=paper_format,
        paper_source=str(paper_path), include_paper=not args.no_paper,
        bindings=bindings_bytes, trace=trace, capture=capture, environment=environment,
        source=checkout.source, signer=SshSigner(key, _PRINCIPAL),
    )
    _self_verify(out, key, paper=None if not args.no_paper else paper)
    return out


def _signer_key(explicit: str | None) -> Path:
    from plumb.cli import DEFAULT_SIGNER_KEY

    return Path(explicit).expanduser() if explicit else Path(DEFAULT_SIGNER_KEY).expanduser()


def _self_verify(out: Path, key: Path, paper: bytes | None) -> None:
    """The built bundle must verify under its own key; refuse it if it does not."""
    pub = key.with_name(key.name + ".pub")
    if not pub.is_file():
        raise BundleRefused(f"no public key at {pub} to verify the bundle")
    with tempfile.TemporaryDirectory(prefix="plumb-verify-") as tmp:
        allowed = Path(tmp) / "allowed_signers"
        allowed.write_text(f"{_PRINCIPAL} {pub.read_text().strip()}\n", encoding="utf-8")
        report = verify_bundle(out, allowed_signers=allowed, principal=_PRINCIPAL, paper=paper)
    if not report.ok:
        detail = "; ".join(f"{cause}: {text}" for cause, text in report.causes)
        raise BundleRefused(f"the bundle does not verify: {detail}")