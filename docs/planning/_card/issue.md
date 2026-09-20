# feat claim-extraction-core — C1 paper-claim extraction (deterministic core)

| Field | Value |
|---|---|
| Type | `feat` |
| Id / slug | `claim-extraction-core` |
| Branch | `feat/claim-extraction-core/aliz` |
| Worktree | `.claude/worktrees/feat-claim-extraction-core` |
| Base | `origin/master` @ `2517aad` |
| Owner | aliz |
| Capability | **C1** — `docs/technical/CAPABILITY_ROADMAP.md:17-30` |
| Phase | **Phase 0 — Prove the wedge** (`docs/ROADMAP.md:21`) |
| Source | Inline brief (no GitHub issue) |

## Source note

`gh issue list --state all` returns empty — Issues are reachable on
`git@github.com:haqaliz/plumb.git` but **no issues have been filed**. This is the
expected greenfield FALLBACK case described in
`.claude/skills/plumb-begin-fast/references/gather-context.md`. The brief below is
the handoff produced by the `plumb-next` skill earlier in this session; it is the
single source the rest of the pipeline reads from.

## Brief

> Build C1 (paper-claim extraction), deterministic core only, per
> docs/technical/CAPABILITY_ROADMAP.md:17-30 and ARCHITECTURE.md:53-61. Scope this
> first slice to plain text/Markdown papers — PDF→text is a later slice, and the
> optional BYOK LLM proposer is OUT of this slice entirely (deterministic spine
> ships first, CLAUDE.md constraint #4). This slice also bootstraps the package:
> pyproject.toml via uv, src/plumb/extract/, and the test harness, since no code
> exists yet (git log shows scaffold-only). Acceptance tests are written FIRST and
> must cover: (a) a typed Claim record carrying reported value, units, a citation
> location in the paper, and the artifact hint it should be derivable from; (b) a
> number appearing in the paper is extracted with a location that round-trips back
> to the exact source span; (c) a value that cannot be grounded in the paper text
> is DROPPED, never emitted as a claim (guardrail: never carried forward as
> DIVERGED); (d) extraction is deterministic — same input, byte-identical output;
> (e) no network access in any test. Do not resolve tolerance policy or locator
> grammar here — ARCHITECTURE.md:155-157 marks them open and non-blocking for C1.

## Why this was picked (from `plumb-next`)

- Lowest unshipped capability id with **no dependencies**
  (`CAPABILITY_ROADMAP.md:29`, sequencing table `:117`).
- On the Phase 0 gate's critical path — the gate needs the honest number
  (`ROADMAP.md:25`), which has no denominator without extracted claims.
- Defines the `Claim` record (`ARCHITECTURE.md:56-58`) that C4's locator binds
  against (`ARCHITECTURE.md:83-85`).
- Testable offline with no fixtures beyond paper text, matching the
  no-network-in-CI mandate (`ARCHITECTURE.md:144`). (C2 against a local path and
  C3 against a local repo are also offline-testable — C1 is not unique here.)

## Carried caveats

1. **R3 — claim-extraction error** (`ROADMAP.md:58`). Deterministic
   "number + units + location" out of a PDF is the hard part; this slice is scoped
   to **plain text / Markdown only**.
2. **This slice bootstraps the repo.** No `pyproject.toml`, no `uv.lock`, no
   `src/` exists. Test-first still holds: the failing test comes before the package.
3. **Tolerance policy** (`ARCHITECTURE.md:154`) and **locator grammar**
   (`ARCHITECTURE.md:156`) are open questions that explicitly do not block C1–C3
   (`ARCHITECTURE.md:158`) — do not resolve them here. Note this defers the
   *policy*, not the presence of a `tolerance_hint` slot on the record; see the
   understanding note.

## Linked issues / PRs

None — tracker is empty.

## Comments

None.

## Attachments

None.
