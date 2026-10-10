# Understanding — notebook-paper (C5/R1 follow-on)

Date: 2026-10-10. Source: `_card/issue.md`. Panel screen + local probe (read-only search
agent + dev-time run on this machine).

## What the work is really asking

Move R1's number using the notebook_cell locator on a **real** paper: fixture a
notebook-computed paper (the dominant failure mode of both prior selection passes,
`docs/planning/gate-paper/survey.md:47-48`), push it through the spine, bind claims through
`notebook_cell` locators, bank the case. Engine half shipped 2026-10-10 (PR #15) — this is
its named successor.

## Selection (rule fixed before selection — `_card/issue.md`)

Screen (web evidence, see screen report): 18+ candidates surveyed across arXiv/PLOS/PeerJ/
F1000/MDPI/Binder markets; **three survived** documentary screening:
1. **Recursive Criticality of AI Self-Improvement** (Burtsev, arXiv:2609.00137, CC BY 4.0;
   repo `burtsev/recursive-criticality-ai`, MIT) — one root notebook, zero RNG, tables
   verbatim in stored cell outputs; numba is the one compiled dep.
2. **Inner Bars & Nuclear Rings in Barred Galaxies** (Erwin, arXiv:2312.12893, CC BY 4.0) —
   deterministic fit params, but unseeded bootstrap uncertainties (Perrin-class noise) and a
   stored-output vs Table 6 AICc mismatch to adjudicate; one of three notebooks is R.
3. **Pressure–Flow of Porcine Thoracic Duct** (Patel, MDPI Bioengineering 12(4):401,
   CC BY 4.0) — deterministic lmfit fits; dataset not bundled (single public Zenodo file —
   dev-time fetch + commit is the intended handling).

Dead-ends recorded (do not re-search): generic notebook-reproducibility meta-research;
PLOS/F1000 tool papers without numbers; MDPI data-on-request papers; arXiv `co:notebook`
skews astronomy/Mathematica/heavy-compiled; Binder repos with stripped outputs.

## Local probe (2026-10-10, dev-time, authorized fetch; this machine)

Candidate 1 probed end-to-end:
- Clone `burtsev/recursive-criticality-ai` (3 files: LICENSE, README, the one notebook —
  a true notebook-only repo).
- Fresh venv (Python 3.13, NumPy 2.1.x, SciPy 1.16.x, matplotlib, networkx, tqdm, ipython,
  **numba** on macOS arm64 — wheel installs and JITs fine), `nbconvert --execute --inplace`
  from scratch: **exit 0**, all 5 figure PDFs regenerated, 20 code cells.
- Re-executed outputs vs committed outputs vs paper text: identical table tokens —
  §3 table `Weak supercriticality 3 12.90 24.73 11.83`, §4.2 `Closed frontier-lab
  competition 10.40 16.53 6.13 / Open competitive ecosystem 9.75 12.58 2.82 / Global
  competition 8.97 13.42 4.45` — present verbatim in both runs and in the paper
  (arXiv HTML). Zero RNG calls in any cell (grep over cell sources).
- The 61×61 (3,721-combination) numba sweep runs to completion inside the execution budget
  (banner `3/3721 infeasible (0.1%)` reproduced); full-notebook wall time to be measured at
  fixture time (screen estimate <5 min; budget ≤20 min).

**Verdict: QUALIFIES.** Deterministic, laptop-CPU, no runtime network, bundled-by-generator
(all data is generated code-side), CC BY paper + MIT code, notebook-only entry, and the
paper's headline numbers are computed in notebook cells — the class the locator serves.

## What the spine will see

- **Entry point**: the fallback notebook rule — no `[project.scripts]`, no root `main.py`,
  one root `*.ipynb` → `jupyter nbconvert --execute --inplace` (C3, built 2026-10-08). The
  checkout's own env must carry `jupyter` + deps (dev-time env build via `tools/`, frozen).
- **Claims rule** (anti-inflation, gate-paper P2): every numeric cell of the paper's §3 and
  §4.2 tables (all rows, including any that do not bind), plus the numeric statistics stated
  in §4 text; each `reported_value.text` verbatim at its span in the normalized paper text.
  Paper member: arXiv PDF (CC BY) — C1 reads text/Markdown/PDF.
- **Bindings**: `notebook_cell` pointers into the canonical outputs arrays (cells 18 and 28
  per the probe enumeration; exact indices re-pinned from the executed record at fixture
  time). `float_repr` where the notebook wrote shortest-repr floats.
- **Uncertainty to record honestly**: the paper's §4.2 rows round to 2 decimals; the
  underlying doubles are full-precision — `float_repr` semantics decide per claim.

## Risks

- **R1 honest-default**: if any claim does not bind or the run drifts, it is `UNVERIFIED`
  with a named cause, reported with denominators.
- **R2**: a wrong cell pointer is auditable (locator + sha256 in evidence);
  `review_required` on every `DIVERGED`.
- **Env drift**: fresh env ≠ paper-era env (the paper is months old); record the frozen
  resolve; run-to-run determinism is the reproducibility claim, version-drift is recorded,
  not assumed away (Perrin precedent: drift note; here the code has no lockfile — README
  states versions, recorded as the declared policy).
- The paper is (2026-08) brand new; its numbers are simulation results with a defined
  deterministic model — a clean REPRODUCED panel is the expected honest outcome; a
  `DIVERGED` is possible if paper and notebook disagree anywhere (probe matched all tokens).