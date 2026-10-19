# Product Hunt launch copy (pre-written, audited against the corpus)

## 0. Field sheet (copy-paste)

| PH field | Value |
|---|---|
| **Name** | `Plumb` |
| **Tagline** (33/60) | `Run the paper. Check its numbers.` |
| **URL** | `https://haqaliz.github.io/plumb/` |
| **Description** (248/260) | see §2 |
| **Topics** (max 3) | Developer Tools · Open Source · Science |
| **Pricing** | Free |
| **Platforms** | Web — it is a cross-platform CLI (macOS, Linux, Windows) |
| **Thumbnail** | `assets/plumb-app-icon-240.png` (240×240) |
| **Gallery** | `plumb-demo.gif` · `plumb-verify.png` · `plumb-corpus.png` · `plumb-site.png` · `plumb-social.png` |
| **Makers** | Aliz (`haqaliz`) |
| **Hunter** | self-hunt |
| **Launch** | Wednesday 21 October 2026, 12:01 AM PT |
| **First comment** | §3 |

---

Everything here is drafted before launch day so the day itself is execution, not invention. Every
factual claim is backed by the repo; §8 is the audit.

**Publishing checklist (owner):** Product name **Plumb**, URL `https://haqaliz.github.io/plumb/`,
gallery in the §4 order, topics in §5, launch 12:01 AM PT on a Tuesday–Thursday.

---

## 1. Tagline (PH limit 60)

> **Run the paper. Check its numbers.** — 33 characters

Alternates, if that reads too terse:

- **Re-run a paper's code. Verify its claims.** (44)
- **Execution-grounded verification for research.** (47)

## 2. Short description (PH limit 260)

> Plumb re-runs a paper's own code on your compute, re-derives each claim from the actual run, and
> returns a per-claim verdict: REPRODUCED, DIVERGED, or UNVERIFIED. Execution decides, never an
> LLM. Open source; the honest number is published with it.

*248 characters — under the 260 limit.*


### Optional PH prompts

**How did you come up with the idea?**
> I kept hitting the same wall in genomics: reproducing and verifying published work was routine
> there, and the rest of the literature had nothing like it. Then the numbers landed — ~3.2% of
> published computational notebooks reproduce at all, and frontier models hit ~6% precision on
> real errata-worthy errors. The obvious fix (an LLM that reads and opines) measurably does not
> work. So I built the part that does: re-run the author's own code and read the number it
> actually printed.

**What's next?**
> A binding proposer (BYOK), so live mode stops needing a hand-written `--bindings` file — that
> is the self-serve unlock. Then the no-code path (statcheck/GRIM-style internal consistency for
> PDF-only papers), and a bigger panel: every runnable paper I can find, probed in public.

**What's the story behind the name?**
> A plumb line is the oldest tool for testing whether something stands true — and "to plumb" is to
> investigate to the bottom. Plumb asks of a paper: does the claim hold when you actually run it?

## 3. Maker comment (the first thing people read)

> Hi Product Hunt — I'm Aliz, and I built Plumb.
>
> Every paper you read is a pile of numbers someone else's code printed. Peer review does not
> re-run that code. LLM judges guess whether the numbers look right, and measurably cannot do it
> (frontier models hit ~6% precision on errata-worthy errors). Plumb does the third thing: it
> **re-runs the paper's own artifacts on your machine** and re-derives each claim from what the
> run actually produced. Execution decides — never a model's opinion.
>
> **Try the 60-second demo** (offline, no environment build, no API key):
>
> ```
> git clone https://github.com/haqaliz/plumb && cd plumb
> uv run plumb verify --from-record fixtures/gate/rcai
> ```
>
> **The honest number:** across 3 real papers and 133 claims, precision and recall are **1/15**
> against owner labels. One republishable discrepancy out of fifteen flagged — because fourteen
> were the artifact's own run-to-run noise and were refuted on review. The corpus records the
> refutations instead of hiding the flags. A verifier reporting 15/15 there would be guessing.
>
> **What it does not do (yet):** live mode needs a hand-written `--bindings` file; there is no
> binding proposer. Most papers ship no runnable code, and figure-only results are unreachable.
> When Plumb cannot decide, it says `UNVERIFIED` — it never dresses that up as `REPRODUCED`.
>
> Point me at a paper with runnable code and I'll probe it during the launch.

## 4. Gallery (in order)

| # | Asset | Caption |
|---|---|---|
| 1 | `assets/plumb-demo.gif` | The 60-second replay: 31 claims, 30 bound, 30 REPRODUCED, 1 UNVERIFIED, 0 DIVERGED. |
| 2 | `assets/plumb-verify.png` | A per-claim verdict table — the artifact, the locator, the re-derived value. |
| 3 | `assets/plumb-corpus.png` | The honest number, with denominators and label authority. |
| 4 | `assets/plumb-site.png` | The landing page, including what a DIVERGED does *not* assert. |
| 5 | `assets/plumb-social.png` | The mark and the one-liner. |

PH thumbnails are square; `plumb-social.png` crops cleanly. The GIF is 1400×620, under 100 KiB.

## 5. Topics

Developer Tools · Open Source · Science · Productivity

## 6. Timing

- **Tuesday–Thursday, 12:01 AM PT** (PH's day boundary). Avoid conference weeks and major model
  launches. Next window: **Wednesday 21 October 2026**.
- **Hunter: self-hunt.** Decided — no outreach required. The listing launches from the owner's
  account; a hunter adds reach, not readiness.
- Post the maker comment immediately; keep the honest number in the first reply, not buried.
- Reply to every comment within the first 6 hours (§10 has the runbook).

## 7. Day-of replies (pre-written)

**"Why not just ask an LLM?"**
> Because it guesses. Frontier models hit ~6% precision on real errata-worthy errors — far below
> the bar for flagging a paper. Plumb re-runs the author's own code and reads the number the run
> printed. A model may extract a claim; only execution assigns the verdict.

**"Your precision is 1/15 — why would I use this?"**
> Because it tells you the truth. The 14 other flags were `DIVERGED` verdicts that owner review
> refuted — the artifact does not run stably enough for its numbers to be paper errors. A tool
> that reported 15/15 would be guessing. The corpus keeps every refutation visible.

**"Does it send my paper or code to the cloud?"**
> No. The paper, repo and data stay on your machine; only hashes and the verdicts you choose to
> publish leave it. There is no server-side execution, and no analytics on the site.

**"Can it verify my paper?"**
> Live mode works today, but it needs a hand-written `--bindings` file mapping claims to the
> values they should match — there is no proposer yet. If your paper ships runnable code, send me
> the repo during the launch and I'll try it (and tell you if it lands `UNVERIFIED`).

**"Is DIVERGED an accusation?"**
> No. It means the artifact's own run contradicts the paper's own claim, at the written
> precision. It is a reproduction discrepancy, never misconduct — see the ethics policy.

**"What about R / Julia / MATLAB papers?"**
> The spine is language-agnostic where the repo exposes an entry point; the first corpus is Python
> and R data-analysis papers whose code actually runs. Coverage is the honest bottleneck: most
> papers ship no code.

## 8. Claim audit (every factual statement above, and its source)

| Claim | Source |
|---|---|
| ~6% precision / ~21% recall for frontier models on errata-worthy errors | SPOT, arXiv 2505.11855 (`CLAUDE.md`) |
| 3 papers, 133 claims, 132 bound, 117 REPRODUCED, 15 DIVERGED, 1 UNVERIFIED | `plumb corpus report`; `docs/METHOD.md` §3 |
| precision / recall 1/15, owner labels | same report |
| 14 of 15 refuted on review; Perrin's unseeded RNG | `fixtures/gate/perrin/README.md`; `docs/METHOD.md` §5 |
| 31 claims / 30 bound / 30 REPRODUCED / 1 UNVERIFIED / 0 DIVERGED for rcai | `fixtures/gate/rcai/README.md`; the replay |
| demo needs no network *once cloned*, no env build, no API key | `plumb verify --from-record` is offline; CI pins it |
| live mode requires `--bindings`; no proposer | `src/plumb/cli/__init__.py`; `CAPABILITY_ROADMAP.md` C4 |
| no egress; verdicts/hashes only | `CLAUDE.md` constraint #2 |
| no analytics on the site | `site/index.html` (no scripts) |

Nothing in this document claims a paper is wrong, that the tool finds errors at a high rate, or
that self-serve verification of an arbitrary paper works today.

---

## 9. If the thread turns hostile

Do not argue in the thread. Reply once, linking:

- the **method and the number**: `docs/METHOD.md`
- **what a DIVERGED is not**: `docs/ETHICS.md`
- the **replayable bundle** for the one confirmed finding: `bundles/agrodesign/`

Then invite the critic to re-run the replay and report what they get. A finding nobody can replay
is an opinion; ours replays.


---

## 10. Launch-day runbook (the only work left)

The repo, the site, the package and the copy are all done. What remains is the act of launching
and the conversation after it.

**T-1 day (10 minutes)**

- [ ] Open https://haqaliz.github.io/plumb/ and click every link.
- [ ] `uvx --from plumb-verify plumb --version` → `plumb 0.1.1`.
- [ ] Paste the maker comment somewhere you can reach it fast (§3).
- [ ] Have the gallery files open: `assets/plumb-demo.gif`, `plumb-verify.png`,
      `plumb-corpus.png`, `plumb-social.png`.

**Launch day (times PT)**

| Time | Do |
|---|---|
| 12:01 AM | Submit the listing (name, tagline, 248-char description, URL, topics). Post the maker comment immediately. |
| 00:05–00:30 | Send the link to 5–10 people who will genuinely engage. No vote rings, no asks for upvotes. |
| 00:30–06:00 | Reply to every comment within ~15 minutes. Keep the honest number in the first reply. |
| 06:00–12:00 | Second pass. For "can it verify my paper?", give the `--bindings` caveat and offer to probe their repo. |
| 12:00–18:00 | Post one substantive update as a comment: a paper you probed live, with its verdict. |
| 18:00–24:00 | Final pass, thank people, log every runnable-paper offer. |

**Never, on the day**

- Argue in the thread. Reply once, link `docs/METHOD.md` and `docs/ETHICS.md`, invite a replay.
- Say or imply "AI found errors". Execution found a discrepancy; the review decided what it means.
- Claim `15/15`, or omit the denominator from `1/15`.
- Ask for upvotes. PH penalises it and it is not how this product earns trust.

**The one-line answer to the worst comment**

> The tool reported that the artifact's own run did not reproduce; the review refuted the finding,
> and the corpus records both. That is the product: it shows its refutations.
