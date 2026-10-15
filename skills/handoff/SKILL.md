---
name: handoff
description: Save and resume work across coding agents with HANDOFF.md, a handoff file at the project root holding the goal, where we stopped, next steps, decisions and failed attempts. Use it to write or update HANDOFF.md when the context window or usage or credit budget runs low, when the user says "save progress", "write a handoff", "tokens almost finished", "context is full", "I'm switching to Codex/Claude/Gemini" or "we'll continue later", at milestones of long tasks, and before stopping with work unfinished. Use it to resume when the user says "continue", "pick up where we left off" or "read the handoff", or a HANDOFF.md exists. Use it to recover a session that ended on a limit, expiry or crash in Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI, OpenCode, Qwen Code, Freebuff or Aider; its bundled script reads their session logs.
compatibility: Any agent that reads Agent Skills (SKILL.md). The bundled script needs Python 3.8+ (standard library only) and uses git when it is there.
metadata:
  version: "2.0.0"
  author: chentaymane
  homepage: https://github.com/chentaymane/handoff
---

# Handoff

Context windows fill up and usage limits hit, often without warning. When a session ends, everything the agent knew (the goal, the plan, what was tried, what is half done) is gone, and the next session, maybe in another tool with another model, starts from zero. `HANDOFF.md` fixes that: one plain Markdown file at the project root that any agent can read to continue in minutes.

This skill has four jobs: **write** the handoff, **resume** from one, **recover** one from a session that died, and, if the user wants, **protect** every session automatically.

## The script

`scripts/handoff.py`, in the same folder as this SKILL.md, does the mechanical part: it reads the session logs that coding CLIs keep on disk, plus git, and writes the facts into HANDOFF.md. Run it from the project folder with `python3` (on Windows `python` or `py -3`):

```
python3 <this-skill-folder>/scripts/handoff.py COMMAND
```

| Command | What it does |
|---|---|
| `now --tool AGENT` | Adds or refreshes the auto section of HANDOFF.md from your own session's log and git. Prints one line. |
| `now --repo-only` | The same with git facts only, for CLIs whose logs it can't read |
| `sessions` | This project's recent sessions from every CLI, newest first, each with its log path |
| `now --from LOG --print` | A digest of one session: requests, last reply, plan, files changed, commands, errors, limits |
| `now --from LOG` | Writes that digest into HANDOFF.md |
| `status` | Recent sessions on this computer, with context used and usage limits |

`AGENT` is the CLI you are running in: `claude`, `codex`, `cursor`, `gemini`, `opencode`, `qwen`, `copilot`, `codebuff` (also Freebuff) or `aider`. In any other CLI (Windsurf, Goose, Amp, Kiro and so on) use `--repo-only`.

The script only reads agents' data, masks API keys and passwords, and only rewrites the lines between `<!-- handoff:auto:start -->` and `<!-- handoff:auto:end -->`. If Python is not available, skip it and add a short "Repo" section yourself from `git status --short` and `git log --oneline -5`.

## 1. Write the handoff

### When

1. **The user asks:** "save progress", "write the handoff", "I'm switching tools", "tokens are almost done".
2. **Your budget is running low.** Watch for any signal: a token or context counter, a "% context left" indicator, a token budget in system messages, a warning about context size, compaction, summarization or usage limits. With about a third left, write it at the next natural pause. Below about 20%, write it now, before any other large step. If a request has just **failed on a usage or credit limit** ("rate limit", "credits required", "limit reached"), write it before anything else: the next request may not go through.
3. **Checkpoints on long tasks:** after a milestone (a feature works, tests pass, a key decision is made), roughly every 30 minutes of active work, before a long or risky operation, and before ending a turn with work unfinished. Most tools never show the remaining budget, and limits, expired sessions and crashes give no warning, so checkpoints are the protection that always works. A checkpoint can be a quick edit of "Where we stopped" and "Next steps".

Skip it for small, quick tasks. If you are unsure whether the budget is running out, write it: it costs a few thousand tokens, while losing the state costs the whole session.

### How

The budget may be nearly gone, so work from what you already know. Don't re-explore the codebase to write the handoff.

1. **Location:** `HANDOFF.md` at the project root: the top of the git repo (`git rev-parse --show-toplevel`) or, outside git, the folder you are working in. Never a temp or home folder, and never the project's README.md.
2. **Existing file?** Read it and update it: keep the goal, decisions and lessons that still hold; rewrite the status, "Where we stopped" and "Next steps". If it describes a *different* unfinished task, don't replace it silently: ask the user, or move it under a "Paused task" heading at the bottom. If the budget is critically low and the file is long, edit only "Where we stopped" and "Next steps".
3. **Write the whole file in one write**, from the template below. One complete write survives a sudden cut-off; a series of small appends may not. Leave the auto section (the marker lines and everything between them) as it is, or leave it out: the script puts it back.
4. **Add the facts:** run `now --tool AGENT` (see above). It records files changed (including through shell commands and commits), recent commands, errors, context and usage limits, the log's path, and the repo state.
5. **Tell the user** in a line or two that HANDOFF.md is saved and how to continue: *open this folder in any coding agent and say "Read HANDOFF.md and continue."*

### Writing it well

The reader is another agent with **zero context**: a different model, in a different tool, maybe days later. It cannot see this conversation.

- **Concrete over vague.** Exact paths, function names, commands, versions, URLs and error messages, copied verbatim. "Fix the bug we found" is useless; "`src/cart.ts:88` computes `total` before discounts are applied; move the discount loop above it" is a handoff.
- **No conversation references.** "As discussed", "the approach above" and "the user's idea" mean nothing to the reader. State the fact itself.
- **Record the why.** Decisions with their reasons, and the user's explicit preferences and rules, so the next agent doesn't undo them.
- **Record what failed.** Approaches tried and why they didn't work: the most expensive knowledge to rediscover.
- **Mark half-done work precisely.** Which files are in an inconsistent state and exactly what remains.
- **Tool-neutral.** Don't depend on one agent's features (slash commands, its to-do tool, its memory). Plain shell commands and plain descriptions work everywhere.
- **No secrets.** Never write API keys, tokens or passwords; say where they live ("`STRIPE_KEY` is in `.env`").
- **Right-sized.** Usually 40 to 150 lines, plus the auto section. The first three sections matter most, which is why they come first.

### Template

```markdown
# HANDOFF: <short task title>

**Updated:** <YYYY-MM-DD HH:MM and timezone> | **By:** <tool / model> | **Status:** In progress / Blocked / Done

> **Next agent:** read this whole file, check it against the repo (`git status`), then continue from "Next steps". Keep this file updated as you work.

## Goal
<What we are building or fixing, why, and what "done" means. Quote the user's request briefly if it helps.>

## Where we stopped
<The exact state right now: what was in progress, which file and function, which command, the exact error, the current hypothesis. Name any half-finished edits.>

## Next steps
1. <Concrete, ordered actions; the first one doable immediately>
2. ...

## Done so far
- [x] <What was completed, files touched, how it was verified>

## Decisions and constraints
- <Decision, and why (alternatives rejected)>
- <User preferences and rules to respect>

## Tried and failed / gotchas
- <What didn't work and why; environment quirks; traps>

## Key files
- `<path>` - <why it matters>

## How to run and verify
- <Install, build, test and run commands; what passes or fails right now>

## Open questions for the user
- <Only the user can decide these, or "None">
```

Drop a section only if it truly has nothing to say (write "None" under Open questions so the reader knows you checked).

## 2. Resume from a handoff

When a session starts in a project with a HANDOFF.md, or the user says "continue", "resume", "pick up where we left off" or "read HANDOFF.md":

1. **Read HANDOFF.md fully** before anything else. The auto section holds facts from the last session's log: files changed, commands, errors, the repo state.
2. **Check it against reality.** Run `git status` and `git log --oneline -5` and compare. If they disagree, trust the repo and mention the difference. If the file looks older than the work in the repo, the last session may have died before updating it: recover that session (section 3) to fill the gap.
3. **Summarize in two or three lines:** the goal, where it stopped, and what you will do next. If an open question blocks the next step, ask it first.
4. **Continue from "Next steps"** and keep HANDOFF.md current with the same checkpoint rules; update the header (date, tool, status) each time.
5. **When the task is done,** set Status to Done with a short final summary, and ask the user whether to keep, commit or delete the file.

## 3. Recover a session that ended without a handoff

A usage limit, an expired session, a closed window or a crash can end a session before any handoff is written, in this tool or another one. The conversation is still on disk, so rebuild the handoff from it instead of asking the user to repeat everything.

1. Run `sessions` in the project folder. It lists this project's recent sessions from every supported CLI, newest first, with the first and latest request, the last reply, whether a usage limit was hit, and the log path.
2. Pick the session that ended. Your own session is usually the newest one and holds only the current request; the one before it is usually the one to recover. If unsure, ask the user, quoting the first requests.
3. Run `now --from "LOG" --print` and read the digest.
4. Check it against the repo (`git status`, `git log --oneline -5`), then write HANDOFF.md from the template as in section 1, and run `now --from "LOG"` to attach that session's facts.
5. Tell the user plainly which parts you reconstructed and which are uncertain, so they can correct you.

## 4. Protect every session automatically (optional)

A skill only runs while an agent is alive and remembers to use it; a usage limit can end a session mid-step. The same script includes a small background watcher that reads the logs of every supported CLI and refreshes HANDOFF.md after each step, with a desktop alert when a limit hits, so the handoff is current even when the session dies.

Offer it once, when it would help: the user just lost a session to a limit, or asks how to never lose work again. It adds a background process and a login item, so run it **only after the user says yes**:

- `install`: adds a `handoff` command, starts the watcher and starts it at every login. `uninstall` undoes all of it.
- `dashboard`: a local web page (127.0.0.1 only) with every project's context use, limits and HANDOFF.md.

## 5. Install the skill in the user's other CLIs

If the user wants this skill in their other coding CLIs too, run `skill install`. It copies this folder into the skills folder of every CLI on the computer (Claude Code, the shared `~/.agents/skills` that Codex, Cursor, Gemini CLI, Copilot CLI and OpenCode read, Qwen Code, Windsurf, Goose, Amp and more). `skill status` shows where it is. See [references/clis.md](references/clis.md) for each CLI's folders and how to call the skill there.

## Notes

- Don't commit HANDOFF.md on your own; ask whether the user wants it in version control (handy for moving between machines or teammates).
- Even if your tool has its own memory or compaction, still write HANDOFF.md: it is the one record every other tool can read.
- Calling it by name: `/handoff` in Claude Code, Cursor, Copilot CLI and Qwen Code, `$handoff` in Codex. In any tool you can also just ask for "the handoff".
