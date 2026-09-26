# Gate fixture: AgroDesign (arXiv:2603.09041)

The first real paper run through Plumb's spine (C2 intake → C3 run → C4 bind & verdict), for
the Phase 0 gate. Planning: `docs/planning/gate-paper/` (the survey, PRD and plan).

## Provenance

| | |
|---|---|
| Paper | Aqib Gul, *AgroDesign: A Design-Aware Statistical Inference Framework for Agricultural Experiments in Python*, arXiv:2603.09041v1 [stat.ME], 10 March 2026 |
| Paper licence | [CC BY 4.0](http://creativecommons.org/licenses/by/4.0/) — `paper.pdf` is redistributed unmodified, with attribution |
| Paper source | `https://arxiv.org/pdf/2603.09041v1`, fetched 2026-09-25 (owner-authorized dev-time fetch) |
| `paper.pdf` SHA-256 | `c2dea137e795ba9f9acc432647d4df3f88b95a3a9c9f5dacfc5c9af8a1abead7` |
| Code | `https://github.com/DeepStatistix/AgroDesign`, Apache-2.0 — **not vendored**; resolved at run time by `tools/gate_run.py` |
| Pinned rev | tag `v1.0.1` = `18b7c29a4f…` ("Paper corrections done", 2026-02-12 — the last code change before the arXiv submission; `src/` is identical to HEAD) |
| Data | the six CSV datasets bundled in the package (`src/agrodesign/datasets/data/`) — synthetic, per the paper's §7 |

## Files

| File | What it is | Written by |
|---|---|---|
| `paper.pdf` | the paper | fetched once |
| `claims.json` | the rule-defined claim set, each claim at its verbatim span in `normalize_text(pdf_to_markdown(paper.pdf))` | `tools/agrodesign_spec.py` |
| `unrepresentable.json` | members of the rule that cannot be a `Claim`, with the reason | `tools/agrodesign_spec.py` |
| `bindings.json` | one binding per claim | `tools/agrodesign_spec.py` |

**The claim rule** (fixed before binding, `docs/planning/gate-paper/prd.md` P2): every numeric
cell of Tables 1–8, and every F, p and Shapiro-Wilk value stated in the prose of §4. That is 75
table cells and 13 prose values; 2 of the prose values ("p ¡ 0.001", §4.1 and §4.2) are the
PDF's own rendering of `<` as `¡` and cannot be parsed, so 86 claims are verified and 2 are
recorded as unrepresentable.

**C1 on this paper:** `extract_claims(pdf_to_markdown(paper.pdf))` recovers **0** of the 86
(290 candidates rejected: 241 `outside_sections`, 49 `reference_numeral`). The claims here are
curated, not extracted; that gap is pinned by `tests/gate/test_agrodesign_fixture.py`.
