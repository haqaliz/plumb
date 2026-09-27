# cli-core — aspect spec

Problem slice: the CLI shell itself — argument parsing, the `[project.scripts]` entry point,
the exit-code contract, and the named-cause failure contract. Everything else (render, replay,
live-spine) plugs into this shell, so this aspect ships first and its contract is load-bearing
for the other three.

## In-scope requirements

- `plumb` console script in `pyproject.toml` (`[project.scripts]`), entry `src/plumb/cli.py`,
  stdlib `argparse` only (no new runtime dependency).
- Subcommand `verify` with the flag set from the PRD:
  `plumb verify <paper> <repo> [--rev REV] [--bindings FILE] [--out DIR] [--from-record DIR]
  [--no-env-build] [--signer-key PATH] [--no-paper] [--json]`.
- Exit-code contract: 0 = every claim decided and run succeeded; 1 = any `UNVERIFIED`, any
  spine failure, any named CLI cause; 2 = usage error. Never 0 with a hidden `DIVERGED`;
  never a traceback on stdout.
- Named CLI causes (`USAGE_ERROR`, `PAPER_UNREADABLE`, `SOURCE_NOT_FOUND`, `REV_NOT_FOUND`,
  `UNSUPPORTED_ARCHIVE`, `ENV_BUILD_FAILED`, `ENTRYPOINT_MISSING`, `ENTRYPOINT_AMBIGUOUS`,
  `WONT_RUN`, `TIMEOUT`, `NO_ARTIFACT`, `STALE_ARTIFACT`, `BINDING_INVALID`, `RECORD_INVALID`,
  `KEY_MISSING`, `BUNDLE_REFUSED`, `SPINE_ERROR`) render as
  `plumb verify: <CAUSE>: <detail>` on stderr, exit 1; usage errors exit 2.
- `--help` documents flags, exit codes, and the bindings-file contract.
- A `main(argv=None) -> int` entry (testable without subprocess) plus a thin
  `if __name__ == "__main__": sys.exit(main())`.
- Injectable seams so render/replay/live-spine can be plugged without touching the shell
  (the shell dispatches to functions the other aspects provide; in this aspect they raise
  `SPINE_ERROR` "not implemented" stubs — no, see acceptance 4: this aspect ships the
  dispatcher with the *failure* paths wired, and the other aspects replace stubs).

## Out-of-scope boundaries

- No `--json` rendering, table layout, record replay, or live spine logic here — only the
  shell, dispatch, and failure contract.
- No `--propose-claims`, no `--tolerance`, no `plumb bundle` subcommand.
- No logging flags, no config files, no shell completion.

## Acceptance criteria (testable, written failing first)

1. `uv run plumb --help` exits 0 and documents the verify subcommand, all flags, exit codes
   and the bindings requirement (test asserts on captured help text).
2. `uv run plumb verify` with no args exits 2 with a usage message naming the missing args;
   an unknown flag exits 2; an unknown `<paper>` kind (not .md/.pdf, not a readable file)
   exits 1 with `PAPER_UNREADABLE`; nothing is printed to stdout on any failure path.
3. Every named cause in the PRD's failure table is emitted by a test that drives its trigger
   through the dispatcher (where the trigger needs a later aspect, the test exercises the
   cause through the injected stub and the mapping layer that the later aspect replaces).
4. `main(argv=...)` is callable in-process and returns the documented exit codes; the
   dispatcher maps engine exceptions (`SourceNotFound`, `RevNotFound`, `EnvBuildFailed`,
   `EntryPointMissing/Ambiguous`, `BindingInvalid`, `PdfInputError`, bundle refusals) to their
   named causes without re-raising.
5. No traceback on stdout for any of the above; stderr lines match
   `^plumb verify: [A-Z_]+: ` exactly.
6. Determinism floor: `--help` output is byte-identical across two invocations in the same
   process (PYTHONHASHSEED variance not required for help text).

## Dependencies and sequencing

First aspect. Render, replay, live-spine plug into its dispatcher. The dispatch table and the
exit-code mapping are the contract the other specs build against.

## Open questions / risks

- Exact stderr phrasing and whether engine cause objects carry a `detail` attribute to render
  (must inspect each exception class; the mapping layer owns this, so it can normalize).
- `PAPER_UNREADABLE` vs `USAGE_ERROR` for a `<paper>` path that doesn't exist: PRD says
  `PAPER_UNREADABLE` (exit 1) — keep it; a wrong *kind* of argument (e.g. `--bindings` without
  a value) is usage (exit 2).