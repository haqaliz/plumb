# Changelog

All notable changes to Plumb are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). The distribution is published to PyPI as
**`plumb-verify`** (the import package and console script are both `plumb`).

## [0.2.0] — 2026-10-21

### Added

- `plumb verify --proposer CMD` — a BYOK binding proposer. The command runs on the user's compute,
  receives the claims and the run's artifact paths, and every proposal is re-grounded against the
  run before it is kept (`PROPOSER_UNGROUNDED` / `MODEL_ONLY_SIGNAL` otherwise). Accepted bindings
  travel in the bundle, so a proposed verification replays without the model. `--bindings` stays
  the default and the two are mutually exclusive.
- `plumb consistency <paper> [--json]` — C7's no-code path: statcheck (t, F, χ², z, r) and GRIM,
  with no SciPy dependency. Labels are `INTERNAL_INCONSISTENCY` / `CONSISTENT` /
  `NOT_APPLICABLE`; never a verdict, and the CLI says so on every run.
- `plumb bundle verify|inspect|pack` — check a bundle without Python, read its declared fields, or
  write a deterministic `.tar`/`.tar.gz` (safe extraction: absolute paths, `..`, links and devices
  refused). `build_bundle(created=...)` adds an optional signed timestamp.
- `plumb verify --timeout-seconds SECONDS` and `--run-dir DIR` — the runner's wall clock and run
  area, with an explicit run directory never wiped.
- Evidence caps in C3 (64 MiB per artifact, 256 MiB per run): an over-cap artifact is refused
  before it is read, never truncated, and `ARTIFACT_TOO_LARGE` / `CAPTURE_LIMIT_EXCEEDED` govern
  every verdict of the run.
- `tools/benchmark.py` and `docs/benchmark/REPORT.md` — the C5 precision/recall report regenerated
  from the committed gate records, with `--check` for CI.
- `docs/findings/agrodesign.md` — the first confirmed finding, prepared but not published, with
  the right-of-reply checklist open and a test pinning its numbers to the signed bundle.

### Documentation

- `fixtures/gate/perrin/reprobe_20261021.md` — the environment half of the Perrin re-probe: the
  generic poetry policy builds the pinned checkout (134 packages, Python 3.11.15). The 12 h run
  was not re-executed, so no drift claim is made.
- C6's remaining gaps are closed except sigstore/transparency logs (deferred with the reason
  recorded); C3's container isolation is deferred with its reason recorded.

## [0.1.1] — 2026-10-19

### Added

- `plumb --version` — prints the installed version and exits 0, so an install is verifiable in
  one command.

### Documentation

- `docs/ETHICS.md` — what each verdict asserts and refuses to assert, when a `DIVERGED` is
  publishable, label authority, and the author right-of-reply process.
- `docs/METHOD.md` — the panel, the verbatim corpus report, how to read precision/recall `1/15`,
  and the known limits.
- `docs/LAUNCH.md` and `docs/LAUNCH-COPY.md` — the launch punch-list and the audited PH copy.
- README: the committed-record replay is now the first command, with an embedded demo GIF and an
  explicit note that live mode needs a hand-written `--bindings` today.
- A static landing page under `site/`, deployed to GitHub Pages by
  `.github/workflows/pages.yml`.

## [0.1.0] — 2026-10-19

First public release: the deterministic spine, end to end, with the honest number published
alongside it.

### Added

- `plumb verify <paper> <repo>` — runs intake → pinned checkout + environment → execution →
  claim binding → per-claim verdict, and writes a signed, replayable bundle with `--out`.
- `plumb verify --from-record DIR` — replays a committed record byte-identically, with no
  network and no environment build.
- `plumb verify --json`, `--bank`, `--no-env-build`, `--signer-key`, `--no-paper`.
- Claim extraction for text and PDF (two-column journals included), with table-cell naming.
- Execution capture for scripts, `[project.scripts]` entry points, `main.py`, and Jupyter
  notebooks (freshness-guarded, content-addressed outputs).
- Locators: JSON pointer, stdout regex, CSV cell, notebook cell, and notebook HTML table cell.
- Signed bundles (`ssh-keygen -Y`, no crypto dependency) and offline bundle verification.
- Discrepancy corpus: `plumb corpus bank` / `plumb corpus report`, with label-authority markers.
- Public panel and honest measurement: 3 real papers, 133 claims, 132 bound, 117 `REPRODUCED`,
  15 `DIVERGED` (14 refuted on owner review, 1 confirmed), 1 `UNVERIFIED` —
  precision/recall **1/15** against owner labels.

### Distribution

- PyPI distribution `plumb-verify` 0.1.0; Python 3.11+; one pinned runtime dependency (`pypdf`).
- Offline test suite (2,077 tests) with network structurally blocked; GitHub Actions CI and a
  tag-driven release workflow using PyPI Trusted Publishing.

### Not in this release

- A binding proposer: live verification requires a user-written `--bindings` file.
- C7 (no-code / internal-consistency checks) and C8 (hosted layer).
