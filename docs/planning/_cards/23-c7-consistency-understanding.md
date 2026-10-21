# Understanding — C7 internal-consistency path (#23)

## What the work really is

A second, weaker evidence path for papers that ship no runnable code. Two deterministic checks,
no model, no network, no new dependency:

| Check | Applies to | Strong direction |
|---|---|---|
| statcheck | an explicitly reported `t/F/χ²/z/r` with df and p | a mismatch: the paper's own statistic and p disagree |
| GRIM | an explicit `mean =` and `N =` in one sentence | an unreachable mean |

## The hard part is false positives, not math

A false `DIVERGED` poisons the project (R2); a false *internal inconsistency* would be worse,
because this path cannot fall back on a run. So the conservatism is load-bearing:

- `t`/`z`/`r` are compared against **both** the two-sided and one-sided p. An unlabeled
  one-sided report is the largest statcheck false-positive class; this kills it.
- A missing df is `NOT_APPLICABLE`, never an assumed df.
- A bound (`p < .001`) is checked as a bound.
- The reported p's own precision defines the band; rounding is never a finding.
- GRIM is gated to one mean and one N in the same sentence, and uses `Decimal`, so the boundary
  (`3.72, N = 40` vs `149/40 = 3.725`) is decided by the same rule the check documents.

## Contradictions / decisions

- **This module never touches `plumb.verify`.** Reusing the verdict vocabulary would invite the
  exact confusion the guardrail forbids; the labels are a separate, smaller vocabulary.
- **`CONSISTENT` is not a clean bill.** GRIM's applicability (integer-valued items) cannot be
  established from prose; the docs and the CLI output both say so.
- **No real no-code paper is in the panel**, so this slice is validated against synthetic papers
  and the documented limits; calibration on a labeled no-code corpus is the next step.

## Pipeline placement

C7; reads C1's text only. No execution, no verdicts.
