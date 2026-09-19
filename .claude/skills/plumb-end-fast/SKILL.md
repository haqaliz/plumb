---
name: plumb-end-fast
description: Use when finishing local work on a Plumb unit of work after the PR is merged and you want to clean up without generating a completion report. Triggers on "plumb-end-fast", "pef", "pef bug 12", "pef feat claim-extraction", "end fast".
arguments: "type id"
---

# Plumb End (Fast Track)

## Overview

Closes out a unit of work's local state after the PR has merged: **master → pull → remove worktree → delete branch**, with a **release phase that is deferred until Plumb has release machinery**. No report (use `plumb-end` / `pe` for that).

**Invocation:** `pef <type> <id>` — e.g. `pef bug 12`, `pef feat claim-extraction`.

- `type` ∈ `bug | feat | feature | task | chore` (normalize `feature` → `feat`)
- `id` = the GitHub issue number, or the slug used at begin time
- Owner is `aliz`
- Branch: `<type>/<id>/aliz`; worktree dir: `.claude/worktrees/<type>-<id>`

Plumb is a single repo, so this runs once. The base branch is **`master`**, never `main`.

## Pipeline

### Phase 0 — Safety check

Before removing anything:

- **Worktree clean?** `git -C <worktree> status --porcelain` must be empty. If not, stop — commit or stash first.
- **Branch merged?** Confirm the PR is merged (`gh pr view <PR> --json state,mergedAt` if reachable). `git branch -d` will refuse an unmerged branch on purpose; do not bypass with `-D` without explicit user OK.
- **You may be inside the worktree being removed.** Resolve the primary checkout first (Phase 1) and run all commands from there.

### Phase 1 — Master, pulled

Resolve the **primary** checkout (not the worktree). The first line of `git worktree list` is the primary:

```bash
PRIMARY=$(git worktree list | head -1 | awk '{print $1}')
```

Switch and pull, fast-forward only:

```bash
git -C "$PRIMARY" checkout master
git -C "$PRIMARY" pull --ff-only origin master
```

### Phase 2 — Remove worktree, delete branch

```bash
WORKTREE_NAME="<type>-<id>"   # e.g. bug-12, feat-claim-extraction
BRANCH="<type>/<id>/aliz"     # e.g. bug/12/aliz, feat/claim-extraction/aliz

git -C "$PRIMARY" worktree remove ".claude/worktrees/$WORKTREE_NAME"
git -C "$PRIMARY" branch -d "$BRANCH"
```

If `worktree remove` refuses due to uncommitted/untracked files, go back to Phase 0 — don't pass `--force` silently.

If `branch -d` refuses because the branch isn't merged into `master`, surface the message — the PR may not be merged, or there are unpushed commits. Don't use `-D` silently.

After both succeed, verify:

```bash
git -C "$PRIMARY" worktree list           # the worktree should be gone
git -C "$PRIMARY" branch --list "$BRANCH" # should print nothing
```

### Phase 3 — Release a new version (DEFERRED — no machinery yet)

**Plumb has no release machinery today**, so this phase does **not** run yet. There is no `pyproject.toml` version, no `CHANGELOG.md`, no `RELEASING.md`, and no `.github/workflows/release.yml`. Cleanup ends at Phase 2. Do **not** hand-craft a release, tag, or publish anything — a release cut without the workflow and the pre-registered rules is exactly the kind of unmeasured, irreversible action the product's own discipline forbids.

**When release machinery lands** (its own unit of work — a `RELEASING.md` + `release.yml` pair), this phase becomes ALWAYS-run and follows these rules, recorded here so they aren't reinvented:

1. **Version from the work type:** `feat`/`feature` → **minor**, `bug`/`chore`/`task` → **patch**. Read the current version and compute the next; confirm the exact `vX.Y.Z` only if ambiguous.
2. **Bump + changelog**, committed to `master`.
3. **CI must be green before tagging.** A release is irreversible (a PyPI version can never be reused, even if yanked).
4. **Tag and push** to trigger the workflow — never `gh release create` by hand, never build/upload artifacts manually.
5. **Verify each channel is live before calling it done** — the honesty rule the product enforces: an unchecked channel is `UNVERIFIED`, not shipped. Report which channels published and surface any failed job.

**Release identity, do not get this wrong (for when it lands):** the release belongs to the **haqaliz** account (`git@github.com:haqaliz/plumb.git`). The PyPI distribution name is not yet decided (`plumb` is likely taken; a name like `plumb-verify` is a candidate) — settle it in the release-machinery unit, don't guess it here.

### Phase 4 — Comment on the issue (optional)

Optional, and only if there's a reachable GitHub issue. Ask first: *"Want me to post a short comment on the issue explaining what we did?"* If the user declines, there's nothing meaningful to say, or there's no issue (the work came from an inline brief), skip.

Otherwise:

1. **Draft a short note** (2–4 sentences). Sources, in order of preference:
   - What the user tells you to say.
   - The merged PR's title + description (`gh pr view <PR>`), if accessible.
   - A best-effort summary from the issue title and the change verb.

   Keep it friendly, light on jargon, no em dashes, no commit hashes, no file paths. The change verb matches the type: `bug → fixed`, `task → done`, `feat`/`feature → shipped`, `chore → done`. Example: *"Shipped the claim extractor. Plumb can now pull a paper's headline numbers out of the text so each one can be checked against what the code actually produces. Let me know if anything looks off."*

2. **Confirm the draft** with the user before posting.

3. **Post it** via `gh`:

   ```bash
   gh issue comment "$ID" --body "<confirmed comment text>"
   ```

   On success `gh` prints the comment URL. Tell the user it landed. If `gh` errors (not authenticated, Issues disabled), surface it and stop — don't retry blindly.

## Common mistakes

| Mistake | Fix |
|---|---|
| Running from inside the worktree being removed | Resolve `PRIMARY` first, run commands from there |
| Checking out / pulling `main` | Plumb's base branch is `master`; `main` doesn't exist |
| Using `git pull` (allowing merge) | Use `--ff-only` |
| Forcing branch delete with `-D` | Only after explicit user OK — `-d` refuses unmerged for a reason |
| Forcing worktree remove with `--force` | Same — never silently discard uncommitted work |
| Worktree dir vs branch confusion | Worktree dir is `<type>-<id>` (e.g. `bug-12`); branch is `<type>/<id>/aliz` |
| Cutting a release | Deferred — Plumb has no release machinery yet; don't hand-craft one |
| Posting the issue comment without confirmation | Draft first, show the user, only post after explicit OK |
| Trying to comment when the work has no issue | Skip Phase 4 — it came from an inline brief |
