---
name: plumb-end
description: Use when finishing local work on a Plumb unit of work after the PR is merged and you also need a completion report on Desktop. Triggers on "plumb-end", "pe", "pe bug 12", "pe feat claim-extraction", "end full".
arguments: "type id"
---

# Plumb End (Full Track)

## Overview

Same cleanup as `plumb-end-fast`, **plus** a completion report at the end via `plumb-report`.

**Invocation:** `pe <type> <id>` — e.g. `pe bug 12`, `pe feat claim-extraction`.
Arguments and conventions are identical to `plumb-end-fast`.

## Pipeline

**REQUIRED SUB-SKILL:** Use `plumb-end-fast` for the cleanup pipeline.

Run its **Phase 0 → Phase 2 exactly as written** (safety check → main + pull → remove worktree → delete branch). Plumb's base branch is **`main`**, never `master`. **Phase 3 (release) is deferred** — Plumb has no release machinery yet, so there is nothing to cut; do not hand-craft one. Only proceed to the report once cleanup verification passes.

### Phase 4 — Completion report

**REQUIRED SUB-SKILL:** Use `plumb-report` with the unit-of-work id and the corresponding type.

The two skills use slightly different type vocabularies — map before invoking:

| `pe` arg | `plumb-report` arg |
|---|---|
| `bug` | `bug` |
| `task` | `task` |
| `chore` | `task` |
| `feat` | `feature` |
| `feature` | `feature` |

Example: `pe bug 12` → invoke `plumb-report` with `bug` + `12` → writes `/Users/aliz/Desktop/bug-12-completion.md`.

`plumb-report` fetches the issue via `gh` when reachable (otherwise works from the merged PR / what we just did) and produces the standard template. If it asks for a screenshot/video, provide one (or hand it to the user to attach), then confirm the file landed on Desktop.

### Phase 5 — Comment on the issue (optional)

Same approach as `plumb-end-fast` Phase 4 — ask the user, draft (using the issue + the just-generated report as source material), confirm, then `gh issue comment <id>`. Skip if there's no reachable issue.

The comment can mirror the report's plain-English summary in a sentence or two. Same tone rules: no em dashes, no jargon, no commit hashes. Skip entirely if the user declines.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running the report before cleanup | Phases 0–2 first; the report is last |
| Skipping the report on purpose | Use `plumb-end-fast` / `pef` instead |
| Passing the wrong type to `plumb-report` | Apply the mapping table (`feat`/`feature` → `feature`, `chore` → `task`) |
| Posting the issue comment before the report | The comment (Phase 5) comes after the report (Phase 4); the report's plain-English summary is good source material |
| Cleaning up against `master` | Plumb's base branch is `main` |
| Trying to cut a release during end | Deferred — Plumb has no release machinery yet |
| Posting the comment without confirmation | Draft first, confirm with the user, then post |
