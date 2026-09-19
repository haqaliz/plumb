---
name: plumb-worktrees
description: Isolate parallel work in the Plumb repo using the Claude Code worktree layout. Use when starting a new bug/feature that should not collide with another running Claude session, or when running the engine and a second branch at once. Covers branch naming, worktree placement under .claude/worktrees, per-worktree uv setup, and cleanup.
allowed-tools: Bash, Read, Write, Edit, Glob
---

# Plumb Worktree Workflow

## When to Use

- You have another Claude session running on a different branch in Plumb and want to start a new bug/feature without colliding.
- You want to run two branches side by side.
- The primary checkout is dirty and switching branches would mix work.

Don't use this for one-off file edits that finish in a single session — a worktree is overhead for nothing if you commit + push before the next branch switch.

## Layout — the official Claude Code pattern

Plumb is a **single repo**. Worktrees live **inside it** at `.claude/worktrees/<name>/`. `.claude/worktrees/` must be in `.gitignore` so worktree contents never show up as untracked files in the primary.

```
/Users/aliz/dev/at/plumb/                                    ← primary (main)
/Users/aliz/dev/at/plumb/.claude/worktrees/bug-12/           ← bug #12 worktree
/Users/aliz/dev/at/plumb/.claude/worktrees/feat-claim-extraction/
```

This is the layout documented at https://code.claude.com/docs/en/worktrees. Older sibling layouts (`plumb.12` next to the repo) work but make `cd` paths awkward and don't auto-trigger `.worktreeinclude` for `claude --worktree`.

`.gitignore` already carries the `.claude/worktrees/` entry, so this is set up. Verify any time with `git check-ignore -v '.claude/worktrees/'` — keep the **trailing slash**: the pattern is directory-only, so a bare `.claude/worktrees` reports "not ignored" whenever the directory doesn't exist yet, which is a false alarm, not a missing rule.

## Branch naming convention

`<type>/<id>/<owner>` — owner is `aliz`. `id` is a GitHub issue number when there is one, otherwise a short descriptive slug.

- `bug/12/aliz`
- `feat/claim-extraction/aliz`
- `feat/binding-verdict/aliz`
- `chore/pin-uv-version/aliz`

Worktree dir name drops the slashes: `<type>-<id>` (e.g. `bug-12`, `feat-claim-extraction`).

## The base branch is `main`

Plumb's base branch is **`main`**. Every branch-from, rebase target, and PR base is `main`.

**Greenfield remote caveat:** the repo was `git init`-ed locally on `main`; there may be **no remote yet** (`git@github.com:haqaliz/plumb.git` is the intended remote, to be created). Until a remote exists and `main` is pushed, branch from **local `main`**:

```bash
git worktree add -b feat/claim-extraction/aliz .claude/worktrees/feat-claim-extraction main
```

Once `origin/main` exists, prefer it (it's the shared truth, and the local ref may be stale):

```bash
git fetch origin main
git worktree add -b feat/claim-extraction/aliz .claude/worktrees/feat-claim-extraction origin/main
```

Never assume a `master` branch — Plumb uses `main`.

## Creating a worktree

### From an existing branch you already pushed
```bash
git worktree add .claude/worktrees/feat-claim-extraction feat/claim-extraction/aliz
```

### Via Claude Code's --worktree flag
```bash
claude --worktree feat-claim-extraction
```
This creates `.claude/worktrees/feat-claim-extraction/` on a new branch `worktree-feat-claim-extraction` based on `HEAD`. Your preferred issue/slug branch names don't match that auto-generated name — when you name the work after an issue, create the branch first (as above), then `git worktree add` with the existing branch. Don't rely on `--worktree` to name it.

## Auto-copying gitignored config (`.worktreeinclude`)

A `.worktreeinclude` at the repo root lists gitignored files that should follow into new worktrees, consumed automatically by `claude --worktree`.

**Plumb currently has no secrets/env files to copy** — the repo is docs-only today. Plumb is BYOK for any LLM-assisted claim extraction/binding proposal, so once a `.env` or local model config exists, create `.worktreeinclude` and list it there, then copy manually when you use bare `git worktree add` (the include is not re-processed after creation):

```bash
# only if such files exist
cp .env .claude/worktrees/feat-claim-extraction/
```

`.venv/`, and the engine's run/artifact dirs (`/runs/`, `/traces/`, `/checkouts/`, `/_sandbox/`, `/corpus/local/` — all already in `.gitignore`) are intentionally **not** copied. The venv is regenerable per worktree (below); the rest are the user's own run data and never leave the box, per the no-raw-data-egress guardrail in `CLAUDE.md`.

**Never copy captured run traces, checkouts, or corpus cases between worktrees.** They're run state tied to the run that produced them, and Plumb's re-derivation guarantees depend on that provenance: a value read against a run it didn't produce is not a verified result, it's an `UNVERIFIED` one at best (freshness guard) and a fabricated one at worst. If a worktree needs run data, point at it by absolute path rather than duplicating it.

## Per-worktree setup (Python core engine — uv)

`.venv` is per-worktree and not shared:

```bash
cd .claude/worktrees/feat-claim-extraction
uv sync                       # build the venv from uv.lock
uv run pytest                 # run the test suite
uv run plumb --help           # the CLI entrypoint
```

⚠️ **Greenfield caveat:** there is **no `pyproject.toml`, no `uv.lock`, and no `src/` yet**. `uv sync` will fail until the Python core is scaffolded, and `uv run pytest` has nothing to run. If your work is the scaffolding, create those files first (test-first: the failing test comes before the package). Skip this section entirely for docs-only work.

## Switching between worktrees

```bash
git -C /Users/aliz/dev/at/plumb worktree list
```

To jump into a worktree's Claude session, `cd` into the worktree dir and run `claude`. Resuming a session started in the primary on the same branch isn't supported — start a fresh session in the worktree.

## Cleaning up

After the PR merges and you no longer need the branch locally (see `plumb-end-fast`):

```bash
git -C /Users/aliz/dev/at/plumb worktree remove .claude/worktrees/feat-claim-extraction
git -C /Users/aliz/dev/at/plumb branch -d feat/claim-extraction/aliz
```

`worktree remove` refuses if there are uncommitted or untracked changes. Either commit them first, or pass `--force` only if you're sure they should be discarded.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `git worktree add` fails: `invalid reference: origin/main` | No remote yet (greenfield) | Branch from local `main`; once pushed, `git fetch origin main` first |
| Branching from `master` | Plumb's base branch is `main` | `master` does not exist — always use `main` |
| Worktree contents appear as untracked in primary | `.claude/worktrees/` not ignored | Already in `.gitignore`; verify with `git check-ignore -v '.claude/worktrees/'` (trailing slash) |
| `uv sync` fails: no `pyproject.toml` | Python core not scaffolded yet (greenfield) | Expected — scaffold it (test-first) or skip for docs-only work |
| `uv run` reinstalls everything on first call in a worktree | `.venv` not shared between worktrees | Expected — `uv sync` once per worktree |
| `pytest` import errors in worktree | Forgot `uv sync` (no venv yet) | `uv sync` in the worktree root first |
| `git worktree add` fails: "already checked out" | Branch is checked out in another worktree (often the primary) | `git checkout main` in the conflicting worktree, then retry |
