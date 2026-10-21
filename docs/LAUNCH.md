# Launch plan — Product Hunt (and everything before it)

Status: **living document**, owner-reviewed. This is the ordered punch-list between today and a
public launch. It is deliberately *not* an engine roadmap — C1..C8 live in
[`technical/CAPABILITY_ROADMAP.md`](technical/CAPABILITY_ROADMAP.md); phases live in
[`ROADMAP.md`](ROADMAP.md).

The one-line goal: **a stranger lands on a URL, installs Plumb in one command, watches a real
replay produce a per-claim verdict in under a minute, and understands the honest number before
they read the hype.**

---

## Where we are (2026-10-19)

The engine is ahead of the distribution. C1–C6 are built and a real panel is measured; what is
missing is the layer that lets a stranger *reach* it.

| Area | State | Evidence |
|---|---|---|
| Verification engine (C1–C6) | **Built** | `src/plumb/`, panel in `fixtures/gate/` |
| Honest measurement | **Published** | 133 claims, precision/recall `1/15` (`README.md`) |
| Signed replayable bundles | **Built** | `bundles/agrodesign/`, `bundles/allowed_signers` |
| Offline test suite | **Green** | 2,080 tests, network blocked (`tests/conftest.py`) |
| CI | **Green on master** | `.github/workflows/ci.yml` (build + py3.11 + py3.13) |
| Installable distribution | **Published** | [`plumb-verify` 0.1.0](https://pypi.org/project/plumb-verify/) |
| Release pipeline | **Working** | `.github/workflows/release.yml` — tag `v0.1.0` published 2026-10-19 |
| 60-second first run | **Works and is the front door** | `README.md` quickstart (replay is the first command) |
| Landing page / URL | **Live** | <https://haqaliz.github.io/plumb/> |
| Launch assets | **Done** | `docs/LAUNCH-COPY.md`, `assets/plumb-demo.gif`, `assets/plumb-social.png` |
| Ethics / right-of-reply policy (R4) | **Written** | `docs/ETHICS.md` |
| Honest-number page | **Written** | `docs/METHOD.md` |
| Self-serve verification of *any* paper | **Blocked** | `--bindings` is required; no proposer |

**Readiness in one sentence:** the repo is launch-ready as a *demonstration of a method*; it is
not yet launch-ready as a *self-serve product*, and the launch should say so plainly.

---

## The reorder (do these in this order)

The tempting order is *engine → benchmark → website → launch*. That order is wrong here: the
engine is already the strongest asset, and every day spent on it before distribution adds nothing
a visitor can touch. The binding constraint is the first 60 seconds and the credibility framing.

| # | Milestone | Why it sits here | Effort | Owner |
|---|---|---|---|---|
| **M0** | **CI safety net** | Every later change needs a green automated gate. Nothing else should land first. | ✅ done | agent |
| **M1** | **Installable distribution** | A launch with "clone this repo" is not a launch. One command or it doesn't count. | ✅ done | agent + owner |
| **M2** | **60-second first run** | The replay demo *is* the product's first impression. Make it the front door, not a footnote. | ✅ done | agent |
| **M3** | **Ethics & framing (R4)** | You will launch a tool that reports `DIVERGED` on named papers. Decide the rules *before* the audience arrives. | ✅ done | owner |
| **M4** | **Honest-number page** | `1/15` is the differentiator for the right audience and a liability for the wrong one. Explain it once, link it everywhere. | ✅ done | owner |
| **M5** | **Launch surface** | A URL that is not GitHub: landing page, install line, try-it command, screenshots. | ✅ live | agent |
| **M6** | **Launch assets & day-of runbook** | Tagline, maker comment, hunter, timing, screenshots, demo video. | ✅ done | owner |

Critical-path total: **~4–5 focused days** of work after the repo changes in this commit. The
self-serve binding proposer was **deliberately not on this path** at launch and has since
landed (#24).

---

## M0 — CI safety net ✅

- [x] `.github/workflows/ci.yml` — offline suite on Python 3.11 (the declared floor) and 3.13.
- [x] Build job: `uv build`, then install the wheel into a clean venv and run `plumb --help`.
- [x] `uv sync --locked` so a stale lockfile fails CI instead of drifting silently.
- [x] `tests/test_package.py` pins the packaging contract: one PEP 440 version, `plumb.__version__`
      matches `pyproject.toml`, the dist name is not the squatted `plumb`, and the console script
      target is importable.

Exit test: a red suite or a wheel that does not answer `--help` blocks the merge.

## M1 — Installable distribution

Repo side (done in this change):

- [x] Distribution name **`plumb-verify`** (the PyPI name `plumb` is an unrelated 2018 library;
      `plumb-verify`, `plumb-cli`, `plumbverify` are free — `plumb-verify` is the honest one).
- [x] Version `0.1.0` in `pyproject.toml` and `plumb.__version__`.
- [x] PEP 639 metadata: Apache-2.0, `license-files`, classifiers, project URLs, keywords.
- [x] `uv.lock` re-locked to the new dist name/version.
- [x] `CHANGELOG.md` with a real 0.1.0 entry, honest about what is *not* in the release.
- [x] `.github/workflows/release.yml` — push a `v*` tag → build → smoke-test → PyPI
      Trusted Publishing (OIDC, no long-lived token) → attach artifacts to the GitHub release.

Owner side (done 2026-10-19):

- [x] Created the PyPI **pending trusted publisher** (PyPI → *Publishing*). Fields as this repo
      requires:

      | PyPI field | Value |
      |---|---|
      | PyPI Project Name | `plumb-verify` |
      | Owner | `haqaliz` |
      | Repository name | `plumb` |
      | Workflow name | `release.yml` |
      | Environment name | `pypi` |

      Two traps that cost a retry here: the project **must** be `plumb-verify` (`plumb` is owned by
      an unrelated older library and is rejected), and "Workflow name" means the **file name**
      under `.github/workflows/` — `release.yml`, not the workflow's `name:` key. A mismatch
      surfaces as `invalid-publisher` at the token exchange; deleting the pending publisher and
      re-adding it with the exact values above fixes it.
- [x] Tagged and pushed the first release: `git tag v0.1.0 && git push origin v0.1.0`.
- [x] Confirmed the one-liner from a clean cache:
      ```bash
      uvx --from plumb-verify plumb --help
      pipx install plumb-verify && plumb --help
      ```
- [x] Added the PyPI badge to `README.md`.

**Known trade-off (documented, not hidden):** the distribution is `plumb-verify` but the import
package and console script are `plumb`, because renaming `src/plumb` is a large, risky refactor for
zero user value. The unrelated 2018 `plumb` package installs a `plumb` module too; both cannot be
installed in the same environment. Note it in the README's install section.

## M2 — The 60-second first run

The best launch demo already exists and needs no network, no environment build, and no API key.
It runs from a checkout (the record and paper are fixtures, not package data):

```bash
git clone https://github.com/haqaliz/plumb && cd plumb
uv run plumb verify --from-record fixtures/gate/rcai
```

That replays the Burtsev notebook paper end to end: 31 claims, 30 bound, 30 `REPRODUCED`,
1 `UNVERIFIED`, 0 `DIVERGED`, byte-identical every time. It is the "aha".

- [x] The replay path works offline (verified 2026-10-19: 31 claims, 30 bound).
- [x] Made it the **first command** in `README.md`, above live verify, with the honest note that
      live mode is expert mode today.
- [x] Decided **not** to bundle the rcai record as package data in 0.1.x: it would redistribute a
      CC BY 4.0 paper inside the wheel and needs a `plumb demo` entry point (new CLI surface +
      tests). The checkout path is the demo; revisit for 0.2 if the landing page wants a one-liner.
- [x] Rendered `assets/plumb-demo.gif` from the **real** replay (5 frames, 8.2 s, ~72 KiB) by
      `tools/record_demo.sh` → `tools/render_demo_gif.py` (SVG frames → `rsvg-convert` → ImageMagick).
      It is a deterministic render of the CLI's actual output, not a screencast — `vhs` produced no
      file on this machine, so the reproducible renderer is the committed path. Embedded in the
      README above the demo command.
- [x] Added `plumb --version` (test-first, `tests/cli/test_cli_core.py::TestVersionIsVerifiable`).
      It is on `master` but **not** in the published 0.1.0 — it ships in 0.1.1, so the README's
      install check stays `plumb --help` until then.

Exit test: someone who has never seen the repo can produce a verdict table in under a minute from
the landing page alone.

## M3 — Ethics & framing (R4) — do not skip

`docs/ROADMAP.md` R4 is rated Medium likelihood / High impact: publishing "errors" against named
papers and authors. A launch multiplies the audience and the risk.

- [x] Wrote `docs/ETHICS.md`: what a `DIVERGED` is and is not (a reproduction discrepancy against
      the paper's own artifacts, **never** an accusation of misconduct); the human-review rule
      before any finding is published; the author right-of-reply process; the retraction path if
      a finding is refuted.
- [x] Stated the labeling policy for the panel: owner labels vs third-party labels, and how
      `1/15` is computed (`plumb corpus report`). See `docs/ETHICS.md` §3.
- [x] Linked `docs/ETHICS.md` from the README (the landing page and PH maker comment links land in
      M5/M6).

Exit test: a journalist could read `docs/ETHICS.md` and correctly describe what Plumb does and does
not claim, without asking you.

## M4 — The honest-number page

The number is `precision/recall 1/15` against owner labels. On Product Hunt that is either your
credibility or your coffin, depending on whether it is explained before it is quoted.

- [x] Wrote `docs/METHOD.md`: the panel (3 papers: AgroDesign, Perrin, Burtsev), what was measured,
      why 14 of 15 `DIVERGED` were refuted on review (Perrin's artifact is not run-to-run
      reproducible at written precision), and what that means (a reproducibility finding, not a
      paper error).
- [x] Published the corpus report output verbatim (`docs/METHOD.md` §3).
- [x] Added a "How to read this number" block to the README (landing page still pending in M5).
- [x] Pre-wrote the answer to the obvious hostile question (`docs/METHOD.md` §8).

Exit test: the number appears with its denominator, its label authority, and its explanation in the
same viewport.

## M5 — Launch surface

PH needs a URL. GitHub is not a product page.

- [x] Landing page: `site/index.html` + `site/styles.css`, static, no JS, deployed by
      `.github/workflows/pages.yml` (`https://haqaliz.github.io/plumb/` once Pages is enabled).
      Headline, the demo GIF, the verdict cards, the honest number, METHOD and ETHICS links.
- [x] Install section with both one-liners (`pipx install plumb-verify`,
      `uvx --from plumb-verify plumb --help`).
- [x] "Try it without installing" is the clone + `--from-record` replay (an honest, static
      demo — nothing executes on a server). The copy says "once cloned" because the clone itself
      needs network.
- [x] Images for the gallery: `plumb-demo.gif` (the replay), `plumb-verify.png` (the verdict
      table), `plumb-corpus.png` (the corpus report), `plumb-social.png` (social card).
- [x] No analytics, no cookies, no third-party requests — stated in the footer. Nothing to
      leak by construction.
- [x] Pages enabled (build type: workflow) and deployed: <https://haqaliz.github.io/plumb/>
      returns 200 and serves the demo GIF.

Exit test: the page answers *what it is*, *how to try it in 60 s*, *what the number is*, and *what
it does not claim* without scrolling into a wall of text.

## M6 — Launch assets & day-of runbook

All copy is pre-written in [`LAUNCH-COPY.md`](LAUNCH-COPY.md), with a claim-by-claim audit (§8).

- [x] Tagline: **"Run the paper. Check its numbers."** (32 chars).
- [x] PH description (under 260 chars), leading with execution, not AI.
- [x] Maker comment: the honest number, the panel, the one-liner, and a direct ask for runnable
      papers to probe.
- [x] Hunter: **self-hunt decided**. Optional, and no outreach is required for readiness.
- [x] Gallery: 5 assets in order with captions. Note: no 60 s video; the 8.2 s GIF is the demo
      (PH treats video as optional).
- [x] Topics: Developer Tools, Open Source, Science, Productivity.
- [x] Timing: Tuesday–Thursday, 12:01 AM PT; avoid conference weeks.
- [x] Day-of prepared: `LAUNCH-COPY.md` §10 is a timeboxed runbook, and §7 has the six expected
      replies. The act itself is launch day.
- [x] Rollback/plan B if the front page turns hostile: point to `docs/ETHICS.md` + the replayable
      bundle, do not argue in the thread (`LAUNCH-COPY.md` §9).

---

## Deferred — do not block the launch on these

These are real gaps. They are listed here so nobody mistakes the launch for "finished".

| Gap | Why it is deferred | When |
|---|---|---|
| **C7 calibration** | The statcheck/GRIM first slice has landed (`plumb consistency`); what remains is calibration against a labeled no-code corpus, which does not exist yet. | When such a corpus exists |
| **Hosted layer (C8)** | Demand-pull by design (`ROADMAP.md`). | Post-PH traction |
| **Module rename `plumb` → `plumb_verify`** | Removes the PyPI collision but touches every import and test. No user value today. | Only if install collisions are reported |

---

## Publishing (copy-paste)

```bash
# one-time owner setup: PyPI pending publisher + GitHub `pypi` environment, then

git tag v0.1.0
git push origin v0.1.0          # release.yml builds, smoke-tests, publishes

# verify from a clean shell
uvx --from plumb-verify plumb --help
pipx install plumb-verify && plumb verify --from-record <record-dir>
```

The release workflow refuses to publish unless the wheel installs standalone and answers `--help`
(`.github/workflows/release.yml`).

---

## Definition of done for launch day

- [x] `uvx --from plumb-verify plumb --help` works from a clean cache (verified 2026-10-19).
- [x] The 60-second replay (from a clone) produces 31 claims / 30 bound in one command.
- [x] The landing page states the honest number and links `docs/ETHICS.md` and `docs/METHOD.md`
      (`site/index.html`; live once Pages is enabled).
- [x] CI is green on `master`; the tag release is on PyPI and attached to the GitHub release.
- [x] The maker comment contains no claim the corpus cannot support (`LAUNCH-COPY.md` §8 audit).
