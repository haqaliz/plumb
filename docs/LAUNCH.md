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
| Offline test suite | **Green** | 2,077 tests, network blocked (`tests/conftest.py`) |
| CI | **Added in this change** | `.github/workflows/ci.yml` |
| Installable distribution | **Added in this change**, publish pending | `pyproject.toml` → `plumb-verify` 0.1.0 |
| Release pipeline | **Added in this change**, owner setup pending | `.github/workflows/release.yml` |
| 60-second first run | **Works**, not yet the front door | `plumb verify --from-record fixtures/gate/rcai` |
| Landing page / URL | **Missing** | — |
| Launch assets (tagline, GIF, copy) | **Missing** | `assets/plumb-social.png` exists |
| Ethics / right-of-reply policy (R4) | **Missing** | risk entry in `docs/ROADMAP.md` |
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
| **M1** | **Installable distribution** | A launch with "clone this repo" is not a launch. One command or it doesn't count. | ✅ repo / ~30 min PyPI setup | agent + owner |
| **M2** | **60-second first run** | The replay demo *is* the product's first impression. Make it the front door, not a footnote. | ~1 day | agent + owner |
| **M3** | **Ethics & framing (R4)** | You will launch a tool that reports `DIVERGED` on named papers. Decide the rules *before* the audience arrives. | ~0.5 day | owner |
| **M4** | **Honest-number page** | `1/15` is the differentiator for the right audience and a liability for the wrong one. Explain it once, link it everywhere. | ~0.5–1 day | owner |
| **M5** | **Launch surface** | A URL that is not GitHub: landing page, install line, try-it command, screenshots. | ~1–2 days | agent + owner |
| **M6** | **Launch assets & day-of runbook** | Tagline, maker comment, hunter, timing, screenshots, demo video. | ~1 day | owner |

Critical-path total: **~4–5 focused days** of work after the repo changes in this commit, plus
owner-only PyPI setup. The self-serve binding proposer is **deliberately not on this path** (see
[Deferred](#deferred--do-not-block-the-launch-on-these)).

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

Owner side (blocking, ~30 min):

- [ ] Create the PyPI project with a **pending trusted publisher**:
      PyPI → *Publishing* → *Add a new pending publisher* → GitHub, owner `haqaliz`,
      repository `plumb`, workflow `release.yml`, environment `pypi`.
- [ ] Create the `pypi` environment in GitHub repo settings (optionally require a reviewer).
- [ ] Tag and push the first release: `git tag v0.1.0 && git push origin v0.1.0`.
- [ ] Confirm the one-liners on a clean machine:
      ```bash
      uvx --from plumb-verify plumb --help
      pipx install plumb-verify && plumb --help
      ```
- [ ] Add the PyPI badge to `README.md` once the release is live (do not add a badge that 404s).

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
- [ ] Make it the **first command** in `README.md`, above the live-verify command.
- [ ] Decide whether to bundle the rcai record as package data so the demo is a true PyPI
      one-liner (`uvx --from plumb-verify plumb demo`), or keep the checkout path. Bundling makes
      the best first impression but redistributes a CC BY 4.0 paper inside the wheel and needs a
      `plumb demo` entry point (new CLI surface + tests). **Not in 0.1.0.**
- [ ] Record a ≤60 s screencast (terminal only, no voice needed): install → replay → the verdict
      summary → `--json` piped to `head`. Save as `assets/plumb-demo.gif` (≤10 MB for PH).
- [ ] Add a `plumb --version` flag (small; makes the install verifiable in one command).

Exit test: someone who has never seen the repo can produce a verdict table in under a minute from
the landing page alone.

## M3 — Ethics & framing (R4) — do not skip

`docs/ROADMAP.md` R4 is rated Medium likelihood / High impact: publishing "errors" against named
papers and authors. A launch multiplies the audience and the risk.

- [ ] Write `docs/ETHICS.md`: what a `DIVERGED` is and is not (a reproduction discrepancy against
      the paper's own artifacts, **never** an accusation of misconduct); the human-review rule
      before any finding is published; the author right-of-reply process; the retraction path if
      a finding is refuted.
- [ ] State the labeling policy for the panel: owner labels vs third-party labels, and how
      `1/15` is computed (`plumb corpus report`).
- [ ] Link `docs/ETHICS.md` from the landing page, the README, and the PH maker comment.

Exit test: a journalist could read `docs/ETHICS.md` and correctly describe what Plumb does and does
not claim, without asking you.

## M4 — The honest-number page

The number is `precision/recall 1/15` against owner labels. On Product Hunt that is either your
credibility or your coffin, depending on whether it is explained before it is quoted.

- [ ] Write `docs/METHOD.md`: the panel (3 papers: AgroDesign, Perrin, Burtsev), what was measured,
      why 14 of 15 `DIVERGED` were refuted on review (Perrin's artifact is not run-to-run
      reproducible at written precision), and what that means (a reproducibility finding, not a
      paper error).
- [ ] Publish the corpus report output verbatim (already reproducible via `plumb corpus report`).
- [ ] Add a one-paragraph "How to read this number" block to the landing page and the README.
- [ ] Pre-write the answer to the obvious hostile question: *"So your tool was wrong 14 out of 15
      times?"* — No: the tool correctly detected that the artifact's own run does not reproduce;
      the *label* refuted the discrepancy, not the verdict.

Exit test: the number appears with its denominator, its label authority, and its explanation in the
same viewport.

## M5 — Launch surface

PH needs a URL. GitHub is not a product page.

- [ ] Landing page (new repo or `site/`, static; reuse `assets/plumb-social.svg` and
      `assets/plumb-corpus.svg`): headline, the 60-second demo command, the verdict table,
      the honest number, `docs/ETHICS.md` link, install line.
- [ ] Install section with the two one-liners (`uvx --from plumb-verify …`,
      `pipx install plumb-verify`).
- [ ] "Try it without installing" — either the bundled replay or a hosted replay of one committed
      record (no engine execution on the server; it is a static replay, not a service).
- [ ] Screenshots: the verdict table (`plumb-verify.png` exists), the corpus report
      (`plumb-corpus.png` exists), and one of the signed bundle verifying.
- [ ] Analytics that do not violate constraint #2: page views only; no paper contents, no egress.

Exit test: the page answers *what it is*, *how to try it in 60 s*, *what the number is*, and *what
it does not claim* without scrolling into a wall of text.

## M6 — Launch assets & day-of runbook

- [ ] Tagline (≤60 chars), e.g. *"Run the paper. Check its numbers."*
- [ ] PH description (≤260 chars) leading with execution, not AI.
- [ ] Maker comment: the honest number, the panel, the one-liner, and a direct ask for runnable
      papers to probe.
- [ ] Hunter: someone credible in research software / open science (optional; self-hunt is fine).
- [ ] Gallery: 3–5 images, demo GIF, 60 s video.
- [ ] Topics: Developer Tools, Open Source, Science, Productivity.
- [ ] Timing: Tuesday–Thursday, 12:01 AM PT (PH's day boundary); avoid a major conference week.
- [ ] Day-of: reply to every comment within the first 6 hours; keep the honest number in the first
      reply, not buried.
- [ ] Rollback/plan B if the front page turns hostile: point to `docs/ETHICS.md` + the replayable
      bundle and do not argue in the thread.

---

## Deferred — do not block the launch on these

These are real gaps. They are listed here so nobody mistakes the launch for "finished".

| Gap | Why it is deferred | When |
|---|---|---|
| **C4 binding proposer (BYOK)** | The single biggest product gap: a stranger cannot verify *their own* paper without hand-writing `--bindings`. It is weeks of work and a capability, not a launch task. | Next unit after launch; the first demand-pull feature |
| **C7 no-code path** | Most papers ship no runnable code. Until statcheck/GRIM lands, the answer to most papers is "cannot verify", which must be framed, not hidden. | Phase 2 |
| **Hosted layer (C8)** | Demand-pull by design (`ROADMAP.md`). | Post-PH traction |
| **`--timeout-seconds` / `--run-dir` knobs** | Should-have hardening from Phase 1; not user-visible on the demo path. | With the proposer |
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

- [ ] `uvx --from plumb-verify plumb --help` works on a machine that never saw the repo.
- [ ] The 60-second replay (from a clone) produces 31 claims / 30 bound in one command.
- [ ] The landing page states the honest number and links `docs/ETHICS.md` and `docs/METHOD.md`.
- [ ] CI is green on `master`; the tag release is on PyPI and attached to the GitHub release.
- [ ] The maker comment contains no claim the corpus cannot support.
