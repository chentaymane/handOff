---
name: handoff
description: Write or update HANDOFF.md - a handoff README that lets any coding agent (Claude Code, Codex, Gemini CLI, Cursor, Copilot, OpenCode, Aider, or a fresh session of the same tool) continue the work exactly where it stopped - the goal, what is done, where we stopped, decisions, failed attempts, and next steps. Use it whenever the context window or token/usage budget is running low (a token counter near its limit, warnings about context size, compaction, or usage limits), when the user says things like "save progress", "write a handoff", "tokens almost finished", "context is full", "I'm switching to Codex/Gemini/Claude", or "we'll continue later", at milestones of long tasks as a checkpoint, and before stopping with work unfinished. Also use it to resume - when the user says "continue", "pick up where we left off", or "read the handoff", or when a HANDOFF.md exists at the project root.
---

# Handoff

Context windows fill up and usage limits hit, often without warning. When a session ends, everything the agent knew — the goal, the plan, what was tried, what is half-done — is gone, and the next session (maybe another tool, another model) starts from zero. `HANDOFF.md` fixes that: one plain Markdown file at the project root that any agent can read to continue in minutes instead of rediscovering everything.

This skill has two jobs: **write** the handoff, and **resume** from one.

## When to write it

1. **The user asks** — "save progress", "write the handoff", "I'm switching tools", "tokens are almost done".
2. **Your budget is running low.** Watch for any signal: a token or context counter, a "% context left" indicator, a token budget in system messages, a warning about context size, compaction, summarization, or usage limits, or a note from a hook saying context is high. With about a third left, write it at the next natural pause. Below about 20%, write it immediately — before any other large step such as reading big files or running commands with long output.
3. **Checkpoints on long tasks.** After a meaningful milestone (a feature works, tests pass, a key decision is made), before a long or risky operation, and before ending a turn with work unfinished. Many tools never show you the remaining budget, and usage limits can end a session mid-task, so checkpoints are the only protection that always works. A checkpoint can be a quick edit of "Where we stopped" and "Next steps".

Skip it for small, quick tasks — a handoff is for work that would be painful to reconstruct. But if you are unsure whether the budget is running out, write it: it costs a few thousand tokens, while losing the state costs the whole session.

## How to write it

Budget may be nearly gone when this runs, so work from what you already know. Don't re-explore the codebase just to write the handoff.

1. **Location:** `HANDOFF.md` at the project root — the top of the git repo (`git rev-parse --show-toplevel`) or, outside git, the directory you are working in. Never overwrite the project's own README.md.
2. **Existing file?** Read it and update it rather than starting over: keep the goal, decisions, and lessons that still hold; rewrite the status, "Where we stopped", and "Next steps". If it describes a *different* unfinished task, don't silently replace it — ask the user, or move it under a "Paused task" heading at the bottom. If the budget is critically low and the file is long, skip the full read and edit only "Where we stopped" and "Next steps".
3. **Write the whole file in one write**, using the template below. One complete write survives a sudden cut-off; a series of small appends may not.
4. **Add the repo snapshot** by running `scripts/snapshot.py` from this skill's folder, with the project as the working directory:

   ```
   python3 <skill-folder>/scripts/snapshot.py      (on Windows: python or py -3)
   ```

   It records the branch, HEAD, recent commits, and uncommitted changes inside HANDOFF.md (between marker comments, replacing any previous snapshot) and prints a single line, so it costs you almost no context. If Python is not available, add a short "Repo snapshot" section yourself from `git status --short`, `git log --oneline -5`, and `git diff --stat`.
5. **Tell the user** in a line or two that HANDOFF.md is saved and how to continue: *open this folder in any coding agent and say "Read HANDOFF.md and continue."*

## Writing it well

The reader is another agent with **zero context** — a different model, in a different tool, maybe days later. It cannot see this conversation.

- **Concrete over vague.** Exact paths, function names, commands, versions, URLs, and error messages copied verbatim. "Fix the bug we found" is useless; "`src/cart.ts:88` computes `total` before discounts are applied — move the discount loop above it" is a handoff.
- **No conversation references.** "As discussed", "the approach above", "the user's idea" mean nothing to the reader. State the fact itself.
- **Record the why.** Decisions with their reasons, and the user's explicit preferences and rules, so the next agent doesn't undo them.
- **Record what failed.** Approaches tried and why they didn't work — the most expensive knowledge to rediscover.
- **Mark half-done work precisely.** Which files are in an inconsistent state and exactly what remains.
- **Tool-neutral.** Don't depend on one agent's features (slash commands, its TODO tool, its memory). Plain shell commands and plain descriptions work everywhere.
- **No secrets.** Never write API keys, tokens, or passwords — say where they live ("`STRIPE_KEY` is in `.env`").
- **Right-sized.** Usually 40–150 lines: enough to resume without re-exploring, short enough to read in one pass. The first three sections matter most, which is why they come first.

## Template

```markdown
# HANDOFF: <short task title>

**Updated:** <YYYY-MM-DD HH:MM and timezone> | **By:** <tool / model> | **Status:** In progress / Blocked / Done

> **Next agent:** read this whole file, compare the Repo snapshot with the real repo (`git status`), then continue from "Next steps". Keep this file updated as you work.

## Goal
<What we are building or fixing, why, and what "done" means (acceptance criteria). Quote the user's request briefly if it helps.>

## Where we stopped
<The exact state right now: what was in progress, which file/function, which command, the exact error, the current hypothesis. Name any half-finished edits.>

## Next steps
1. <Concrete, ordered actions - the first one doable immediately>
2. ...

## Done so far
- [x] <What was completed - files touched - how it was verified>

## Decisions and constraints
- <Decision - reason (alternatives rejected)>
- <User preferences and rules to respect>

## Tried and failed / gotchas
- <What didn't work and why; environment quirks; traps>

## Key files
- `<path>` - <why it matters>

## How to run and verify
- <Install / build / test / run commands; what currently passes or fails>

## Open questions for the user
- <Only the user can decide these - or "None">
```

Drop a section only if it genuinely has nothing to say (write "None" under Open questions so the reader knows you checked).

## Resuming from a handoff

When a session starts in a project with a HANDOFF.md, or the user says "continue", "resume", "pick up where we left off", or "read HANDOFF.md":

1. **Read HANDOFF.md fully** before anything else.
2. **Check it against reality.** Run `git status` and `git log --oneline -5` and compare with the Repo snapshot — the user or another agent may have changed things since. If they disagree, trust the repo and mention the difference.
3. **Summarize in two or three lines:** the goal, where it stopped, and what you will do next. If an open question blocks the next step, ask it first.
4. **Continue from "Next steps"** and keep HANDOFF.md current with the same checkpoint rules — update the header (date, tool, status) each time.
5. **When the task is done**, set Status to Done with a short final summary, and ask the user whether to keep, commit, or delete the file.

## Notes

- Don't commit HANDOFF.md on your own; ask whether the user wants it in version control (handy for moving between machines or teammates).
- Even if your tool has its own memory or compaction, still write HANDOFF.md — it is the one record every other tool can read.
- Invoking by name: `/handoff` in Claude Code and Copilot, `$handoff` in Codex. In any tool you can also just ask for "the handoff".
