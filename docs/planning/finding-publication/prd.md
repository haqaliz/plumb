# PRD — prepare the first confirmed finding for publication

Issue: #25.

## Requirements

- **R1** — `docs/findings/agrodesign.md`: paper, pinned artifact, claim id, reported and located
  values, delta and band, replay commands, review record.
- **R2** — what the finding asserts and does not assert, framed as a reproduction discrepancy per
  `docs/ETHICS.md`; no misconduct language.
- **R3** — the right-of-reply checklist is open (owner sign-off, contact, 14-day window, outcome),
  with a draft message that has not been sent.
- **R4** — a test pins the note's claim id and numbers to the signed bundle's single `DIVERGED`.
- **R5** — `docs/ETHICS.md` points at `docs/findings/` and the publication rule.

## Non-goals

- Contacting the authors, publishing anything, or filing upstream issues.
- Any engine or CLI change.

## Acceptance

`tests/bundle/test_published_finding.py`; full suite green.
