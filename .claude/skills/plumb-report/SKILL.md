---
name: plumb-report
description: Use when a Plumb unit of work (bug, task, feature) is done and you want a brief, friendly, non-technical completion note saved on Desktop to share with the team.
allowed-tools: Read, Grep, Glob, Bash, Write
arguments: "type id"
---

# Plumb Completion Note

A short, friendly, non-technical heads-up that a unit of work is done. Written like a teammate would write it — no jargon, no commit hashes, no checklists. Just one plain-English sentence about what changed, plus a link and a screenshot.

## Arguments

- `type` ∈ `bug | task | feature`
- `id` = the GitHub issue number, or the slug used at begin time

Usage: `/plumb-report bug 12` or `/plumb-report feature claim-extraction`.

## When to use

- A unit of work is finished and you want to let the team know in a human way.
- You've closed (or are about to close) a GitHub issue, or merged its PR.

## Output

Markdown file saved to `/Users/aliz/Desktop/{type}-{id}-completion.md`.

Examples:
- `/Users/aliz/Desktop/bug-12-completion.md`
- `/Users/aliz/Desktop/task-pin-uv-version-completion.md`
- `/Users/aliz/Desktop/feature-claim-extraction-completion.md`

## The template

One template, three small verb tweaks. Keep it warm, short, and free of technical detail.

```markdown
## #{id} - {Feature or area} - {Short Title}

Hey! Quick note that this one's {verb}.

**What changed (in plain words):**
{One or two friendly sentences. What's different for the user now. No jargon. No em dashes.}

**See it live:** {link to the PR, or the CLI command}
**Screenshot/video:** {attached, or link}

If anything looks off or you'd like a tweak, just say the word.
```

Verb per type:

| Type | Verb |
|---|---|
| `bug` | fixed |
| `task` | done |
| `feature` | shipped |

## Tone rules

- Write like you're messaging a teammate, not filing a ticket.
- Plain English only. Swap out words like *claim extraction, artifact, pinned environment, re-derivation, locator, binding, tolerance, verdict, corpus, freshness guard, content-addressed, bundle* for everyday phrasing. "Re-runs the paper's code and checks its numbers hold" beats "execution-grounded per-claim re-derivation".
- No checklists, no testing matrices, no commit hashes, no branch names, no file paths — those live in the PR, not in this note.
- Two or three short paragraphs max. If it reads like docs, trim again.
- **Never use the em dash character `—` in the note.** It's a tell that an AI wrote it. Use a comma, a period, or a regular hyphen with spaces (`-`) instead.
- A friendly closer is welcome ("Let me know what you think.", "Happy to revisit if needed.").

## Don't over-claim (this one matters here)

Plumb's whole product promise is that a verdict never says more than it checked, and the note has to hold the same line. Plain language is not a licence to inflate:

- Don't say a paper's result is "reproduced" or "proven correct" when the work only made it *runnable* or *captured*, or when the honest verdict was `UNVERIFIED`. Say what it actually does.
- Don't imply a `DIVERGED` finding is an accusation of misconduct — it's a reproduction discrepancy against the paper's own artifacts. Say it plainly.
- Don't imply coverage we don't have. Plumb sees the claims it can bind to a real run; a paper whose code won't run stays `UNVERIFIED`. If that's relevant, say it simply.
- If the work is a slice of a bigger capability, say it's a first step rather than implying the whole thing landed.

An honest small claim reads better to a teammate than an oversold one, and it's the same discipline the engine enforces.

## Workflow

1. **Get the context.** Prefer the GitHub issue if reachable; otherwise use the merged PR or what we just did:
   ```bash
   gh issue view "$ID" 2>/dev/null || gh pr view "$PR" 2>/dev/null
   ```
   If neither resolves, write the note from the work you just completed in this session.
2. **Distill** the change into one or two plain sentences. Resist the urge to add detail.
3. **Pick the "See it live" target** that fits the work: the merged PR link, or the exact CLI command a teammate would run (`uv run plumb verify <paper> <repo>`). For engine-only work with no visible surface yet, the PR is the honest answer — don't invent a demo that doesn't run.
4. **Ask the user for a screenshot or short video** if one isn't already on hand.
5. **Write** the note to `/Users/aliz/Desktop/{type}-{id}-completion.md` and tell the user it's ready.

## Optional: cross-check

Only include if the user explicitly asks for it. Append one short, friendly line:

```markdown
**Also checked:** {a couple of related areas you peeked at, in plain words}
```

Don't add this by default — it makes the note look like an audit.

## Example (feature)

```markdown
## #34 - Verify - Check a paper's numbers against its code

Hey! Quick note that this one's shipped.

**What changed (in plain words):**
We can now take a paper and the code behind it, re-run that code, and check each headline number against what the code actually produces. If a number does not hold up, it gets flagged with the evidence, instead of being taken on trust.

**See it live:** run `uv run plumb verify <paper> <repo>` and watch the per claim results
**Screenshot/video:** attached

If anything looks off or you'd like a tweak, just say the word.
```
