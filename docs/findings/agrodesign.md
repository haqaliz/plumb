# Finding: AgroDesign reports 0.034; its own code prints 0.03455

Status: **owner-confirmed, not published, not sent to the authors.** This note is the artifact
that would accompany publication; the last section is the human checklist that is still open.

## What is reported and what the artifact prints

- **Paper:** AgroDesign, arXiv:2603.09041 (`https://arxiv.org/pdf/2603.09041v1`).
- **Artifact:** `https://github.com/DeepStatix/AgroDesign.git`, pinned at
  `18b7c29a4f8de3dc9260b9fa42849e5a74097825`.
- **Claim (§4.1, Shapiro-Wilk normality of CRD residuals):** `p = 0.034`.
- **The paper's own code, run by Plumb:** `p = 0.03455`.
- **Claim id:** `424724672c5a746a42bdb2a701f0ecf0c3b4d1549125aba38fad72b07c9c376a`.
- **Delta:** `0.00055`; the paper's written precision (3 decimals) gives the band
  `[0.0335, 0.0345]`, and `0.03455` is outside it.

The other 85 rule-defined claims in the panel `REPRODUCED`. This is the single `DIVERGED`.

## How a third party checks it

Offline, signature, members, grounding and re-derived verdicts:

```bash
uv run python -c "from plumb.bundle import verify_bundle
r = verify_bundle('bundles/agrodesign', allowed_signers='bundles/allowed_signers',
                  principal='plumb-bundle')
print(r.ok, [(v.claim_id[:8], v.reported_text, v.located_text) for v in r.verdicts.verdicts
             if v.verdict == 'DIVERGED'])"
```

Expected: `True [('42472467', '0.034', '0.03455')]`.

Networked, against the upstream code at the pinned commit, in the frozen environment:

```bash
uv run tools/bundle_replay.py bundles/agrodesign bundles/allowed_signers plumb-bundle
```

Expected: `result: RUN_REPLAYED` with the bundle's run id
`96646995704bf25c83f5e0393359845f09c4d959bae5f036410821b14fa567b1` (recorded in
`bundles/README.md`).

## What this asserts, and what it does not

It asserts that the paper's own artifact, at the signed commit and in the recorded environment,
prints `0.03455` where the paper reports `0.034` — that the reported value does not match the code
that produced it at the precision the paper wrote.

It does **not** assert that the analysis is wrong, that the paper's conclusions change, that the
authors acted in bad faith, or that any other claim is affected. `0.034` and `0.03455` are on the
same side of the conventional 0.05 threshold; this is a reporting discrepancy, not a finding about
the result's meaning. The verdict is `DIVERGED` against the paper's own claim, `review_required` by
construction, and nothing here is a misconduct claim (`docs/ETHICS.md` §1–§2).

## Review record

- The `DIVERGED` was reviewed by the owner on **2026-09-27** and confirmed as a genuine reporting
  discrepancy (the paper's `0.034` against its own code's `0.03455`);
  `docs/technical/CAPABILITY_ROADMAP.md` C4.
- The bundle verifies offline, from a fresh clone, and its run replays byte-identically
  (`bundles/README.md`, run replay 2026-09-27).
- The binding was reviewed by eye: it reads the `Shapiro-Wilk normality test` line of the CRD
  section from the program's stdout — the same line the paper's own script prints.

## Right of reply — open

Per `docs/ETHICS.md`, no finding is published before the authors have a chance to respond, and
only after the owner signs off. None of the following has happened yet:

- [ ] Owner sign-off to publish.
- [ ] Find the corresponding author's current address and send the draft below.
- [ ] Give at least 14 days for a response; record the date sent and any reply.
- [ ] If a correction is published upstream, update this note with a link and label it as resolved.
- [ ] If the finding is refuted, withdraw it publicly and record the refutation — do not argue.

Draft (not sent):

> Subject: A reproduction discrepancy in arXiv:2603.09041 (AgroDesign)
>
> Hello — I run Plumb, an open-source tool that re-runs a paper's own code and checks the paper's
> reported numbers against what the code prints. On your paper, at commit 18b7c29, the CRD
> Shapiro-Wilk p-value prints as 0.03455, while §4.1 reports 0.034. The rest of the panel's 85
> claims reproduce.
>
> This may well be a rounding or transcription difference, and it does not change any conclusion
> I can see. I am writing before publishing anything, in case you want to correct it, clarify it,
> or tell me what I have got wrong. The signed, replayable bundle is attached so you can check it
> yourself without trusting me.
>
> Thank you for the code and the paper — the artifact ran out of the box.
