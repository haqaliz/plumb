# PRD — C3 resource caps beyond the timeout

Issue: #21. First half of the two named C3 gaps.

## Requirements

- **R1 — caps exist.** `CaptureCaps(max_artifact_bytes=64 MiB, max_total_bytes=256 MiB)`, both
  `None`-able, threaded through `run_and_capture(..., caps=...)`.
- **R2 — refusal, not truncation.** An over-cap file is refused from `stat` **before** it is
  read; an over-cap stream is refused before it is stored. No partial bytes enter the object
  store.
- **R3 — named causes.** `ARTIFACT_TOO_LARGE` (one artifact) and `CAPTURE_LIMIT_EXCEEDED` (total)
  are recorded on the capture and trace, appear in C4's closed vocabulary, and govern every
  verdict — a capped run is never `REPRODUCED`, never `DIVERGED`, and never silently
  `NO_ARTIFACT`.
- **R4 — defaults are safe and tests are offline.** Existing runs under the caps are unchanged
  (no cause, same artifacts, same run id).
- **R5 — the catalogue stays honest.** A test proves each new cause is emitted through a real
  run and reaches a verdict.

## Non-goals

- Container isolation: deferred, reason recorded (Docker in CI + a new dependency; C2's
  subprocess posture stands).
- Streaming the subprocess pipes: `shortcut:` documented at the call site.

## Acceptance

`tests/run/test_caps.py` and the two new rows in `tests/verify/test_cause_catalogue.py`; full
suite green, offline.
