# Changelog

All notable changes to Plumb are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). The distribution is published to PyPI as
**`plumb-verify`** (the import package and console script are both `plumb`).

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
