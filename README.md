# Memory-Skill: `handoff`

**Never lose your work when the tokens run out.**

`handoff` is one skill for all your coding agents. When the context window or your usage limit is almost used up, the agent writes a **`HANDOFF.md`** file in your project: what we are building, where we stopped, what to do next, and everything another agent needs to know. Then you open the project in any other tool, or a new session, and say:

> **Read HANDOFF.md and continue.**

It works with Claude Code, Codex, Gemini CLI, Antigravity, Cursor, GitHub Copilot, OpenCode, and any other tool that supports [Agent Skills](https://agentskills.io).

```
 Claude Code                                 Codex / Gemini / Cursor / new session
 (tokens almost finished) --> HANDOFF.md --> "Read HANDOFF.md and continue."
```

## What's in this repo

| Path | What it does |
|---|---|
| `handoff/SKILL.md` | The skill. Tells the agent when to write the handoff, what to put in it, and how to resume from one. |
| `handoff/scripts/snapshot.py` | Adds an automatic "Repo snapshot" to HANDOFF.md: branch, recent commits, uncommitted files. Python 3, no packages needed. |
| `handoff/scripts/context_monitor.py` | Optional Claude Code hook: measures how full the context window is and tells Claude to write the handoff in time. |
| `install.py` | Installs the skill for all your tools, and optionally the hook and rules. |
| `HANDOFF.md` | A real handoff, written while building this repo. |

## Install

You need Python 3 for the installer and the snapshot script (the skill itself works without it).

```bash
python install.py --hooks --rules
```

- With no options it only copies the skill. `--hooks` and `--rules` are explained below.
- It copies instead of linking, so run it again after you change the skill.
- `--dry-run` shows what would change. `--uninstall` removes everything it added.

Where the skill goes:

| Folder | Read by |
|---|---|
| `~/.claude/skills/handoff` | Claude Code (OpenCode reads it too) |
| `~/.agents/skills/handoff` | Codex, Gemini CLI, Cursor, GitHub Copilot, OpenCode, Amp, Goose, and most other Agent Skills tools |
| `~/.gemini/config/skills/handoff` | Antigravity (IDE, app and CLI), only if `~/.gemini` exists |

Want it in one project only? Copy the `handoff` folder to `<project>/.agents/skills/handoff` (Codex, Gemini CLI, Antigravity, Cursor, Copilot, OpenCode) and `<project>/.claude/skills/handoff` (Claude Code).

### `--hooks`: automatic warning in Claude Code

An agent can't always see how full its context is. In Claude Code this hook measures it after every tool call and every message you send, and tells Claude what to do:

- at **60%** full: write HANDOFF.md at the next natural pause
- at **75%** full: write HANDOFF.md now, before anything else
- right after **auto-compaction**: re-read HANDOFF.md (or write one while the summary is fresh)
- at **session start**: if the project has an unfinished HANDOFF.md, Claude is told it exists

Using 1M-context models? Install with `--window 1000000`. Otherwise the first warnings come too early (at 120K and 150K tokens) until usage passes 200K and the hook switches to 1M by itself.

Settings are environment variables; you can put them in the `env` block of `~/.claude/settings.json`: `HANDOFF_CONTEXT_WINDOW` (default 200000), `HANDOFF_SOFT_PCT` (60), `HANDOFF_URGENT_PCT` (75).

The hook adds about 0.3 s per tool call on Windows (Python start-up). If that bothers you, delete its `PostToolUse` entry in `~/.claude/settings.json`; you still get the check each time you send a message.

Why only Claude Code? Codex hooks are experimental and don't run on Windows, and Gemini CLI's `PreCompress` hook can't send a message to the model. In the other tools the skill still works: when the agent sees a warning, at milestones, and when you ask.

### `--rules`: tell every agent to look for HANDOFF.md

Adds this rule to the global instructions file of each tool you have (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`, `~/.config/opencode/AGENTS.md`):

> - At the start of a session, if the project root has a HANDOFF.md whose Status is not Done, read it before starting work and offer to continue from its "Next steps".
> - When the context window or usage budget is running low, when the user is about to switch tools, and at milestones of long tasks, write or update HANDOFF.md with the `handoff` skill.

Cursor and Copilot have no global instructions file: paste the same two lines into Cursor Settings > Rules > User Rules, and into a project's `AGENTS.md` for Copilot.

## Use it

| Tool | Ask for a handoff |
|---|---|
| Claude Code | `/handoff` |
| Codex | `$handoff` |
| GitHub Copilot | `/handoff` |
| Gemini CLI, Antigravity, Cursor, OpenCode, others | "write the handoff" |

To continue in any tool: open the project and say **"Read HANDOFF.md and continue."**

You don't always have to ask. The agent writes or updates HANDOFF.md by itself when:

- it sees the budget running low (a token counter, a context or usage warning, or the Claude Code hook);
- it finishes a milestone of a long task (a checkpoint, in case the session stops suddenly);
- it is about to stop with the work unfinished.

## What goes in HANDOFF.md

It is written for an agent that knows nothing about your conversation:

1. **Goal**: what we are building and what "done" means
2. **Where we stopped**: the exact file, command, error, and half-finished edits
3. **Next steps**: ordered, concrete actions
4. **Done so far**, **Decisions and constraints**, **Tried and failed / gotchas**, **Key files**, **How to run and verify**, **Open questions**
5. **Repo snapshot**: added automatically by `snapshot.py`

The full template is in [handoff/SKILL.md](handoff/SKILL.md), and [HANDOFF.md](HANDOFF.md) is a real example.

## Good to know

- **Usage limits give no warning.** A message like "5-hour limit reached" can stop a session at any moment, and the agent can't see it coming. That's why the skill writes checkpoints at milestones: your handoff is never more than one milestone old. If you know you are close to a limit, just say "write the handoff".
- **One file per project.** Each session updates the same HANDOFF.md instead of adding new ones.
- **Not committed automatically.** Commit HANDOFF.md if you want to continue on another computer.
- **No secrets.** The skill tells agents never to write keys or passwords into it, and the snapshot removes credentials from remote URLs.

## Uninstall

```bash
python install.py --uninstall
```
