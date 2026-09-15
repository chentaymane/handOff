# HANDOFF: Cross-CLI "handoff" skill (Memory-Skill repo)

**Updated:** 2026-09-16 00:35 +0100 | **By:** Claude Code desktop / claude-opus-5 | **Status:** Done

> **Next agent:** read this whole file, compare the Repo snapshot with the real repo (`git status`), then continue from "Next steps". Keep this file updated as you work.

## Goal
Build an Agent Skill that works in every coding agent (Claude Code, Codex, Gemini CLI / Antigravity, Cursor, Copilot, OpenCode, ...): when the context window or usage budget is nearly used up, the agent writes `HANDOFF.md` (goal, where we stopped, next steps, decisions, failures, repo snapshot) so any other tool or a fresh session can continue. The user's words: "when the token has close to finish create a readme tell all about what we wana do and where we are stop and all information for other cli can use it". Done = skill + scripts + installer + README, tested, and installed with the user's permission.

## Where we stopped
Finished and installed. `python install.py --hooks --rules` ran on 2026-09-16: the skill was copied to `~/.claude/skills/handoff`, `~/.agents/skills/handoff` and `~/.gemini/config/skills/handoff`; the hook was added to `~/.claude/settings.json` for SessionStart, UserPromptSubmit and PostToolUse (window left on Auto, so 200K until usage passes 200K, then 1M); the rule block was added to `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md` and `~/.config/opencode/AGENTS.md` (the installer created all four). Claude Code loaded the skill straight away, without a restart. The repo was committed and pushed to `origin/main`.

## Next steps
1. **User's own live test** (their choice instead of an automated A/B run): open this folder in Codex (`$handoff`), Antigravity, Cursor or OpenCode and say "Read HANDOFF.md and continue" to confirm the cross-tool handoff works.
2. If warnings arrive too early in 1M-token sessions, set the real window: re-run `python install.py --hooks --window 1000000`, or add `HANDOFF_CONTEXT_WINDOW` to the `env` block of `~/.claude/settings.json`.
3. Optional, not done: full A/B eval with helper agents over three scenarios (switch tools mid-task, resume from a handoff, react to the hook reminder).
4. Optional, not done: package the skill as a shareable `.skill` file with skill-creator's `package_skill.py` (copy it to the scratchpad first, see gotchas).

## Done so far
- [x] `handoff/SKILL.md` - passes the skill-creator validator (description 893 chars, 104 lines).
- [x] `handoff/scripts/snapshot.py` - tested: repo with no commits, upstream ahead/behind, credential redaction, CRLF and UTF-16 files, non-git folder, run from a subfolder, idempotent, HANDOFF.md left out of the file list.
- [x] `handoff/scripts/context_monitor.py` - tested with synthetic and real transcripts: soft 60% / urgent 75% once per session, re-armed after a `compact_boundary` entry, sidechain lines and subagent events ignored, SessionStart pointer (quiet when Status is Done), compact reminder, bad input exits 0. About 330 ms per call here, almost all Python start-up.
- [x] `install.py` - tested in a fake home (`USERPROFILE` override): dry run changes nothing; install merges with existing hooks, env and a CRLF CLAUDE.md; a second run adds no duplicates; uninstall restores settings.json (JSON-equal) and CLAUDE.md (byte-identical) and keeps a `settings.json.before-handoff` backup.
- [x] `README.md` - install, per-tool folders, hook, rules, usage, limits, uninstall.
- [x] Installed on this machine and verified (skill folders, settings.json, four rule files, hook run from the installed copy).
- [x] Committed and pushed to https://github.com/chentaymane/Save-Skill (the GitHub repo was renamed from Memory-Skill; the old URL still redirects, and the local remote is still set to it)

## Decisions and constraints
- Output file is `HANDOFF.md` at the project root; never overwrite the project's README.md.
- Frontmatter uses only Agent Skills spec fields (`name`, `description`) so every tool accepts it.
- Skill folders: Claude Code reads only `~/.claude/skills`; Codex, Gemini CLI, Cursor, Copilot and OpenCode read `~/.agents/skills`; Antigravity (IDE, app, CLI) reads `~/.gemini/config/skills` and not `~/.agents/skills` (checked in docs, Sept 2026).
- Only Claude Code gets automatic hooks: Codex hooks are experimental and unavailable on Windows; Gemini's `PreCompress` hook cannot prompt the model.
- Hooks use exec form (`command` = absolute python.exe, `args` = [script path]) to avoid shell quoting on Windows. `additionalContext` is a plain string inside `hookSpecificOutput`.
- Context estimate = input + cache_creation + cache_read + output tokens of the last main-thread assistant entry in the transcript JSONL. Default window 200K (switches to 1M once usage passes 200K); env vars `HANDOFF_CONTEXT_WINDOW`, `HANDOFF_SOFT_PCT` (60), `HANDOFF_URGENT_PCT` (75).
- The user's Claude Code sessions actually use a 1M window (a past session auto-compacted at about 970K tokens, this one passed 200K without compacting), but they chose Auto so the hook also behaves correctly if they switch to a 200K model.
- Ask before installing, editing global config, committing, or spawning subagents.

## Tried and failed / gotchas
- WebFetch summaries of the Claude Code hooks docs were wrong (said `additionalContext` is an object). Trust the raw docs: https://code.claude.com/docs/en/hooks.md
- The skill-creator folder (under `AppData\Roaming\Claude\...`) is app-virtualized: Python cannot open its scripts from Git Bash or PowerShell. Read such a script and write a copy into the scratchpad, then run the copy (that is how `quick_validate.py` was run).
- Python start-up flags (`-S`, `-I`) do not make the hook faster on this machine.
- Machine: Windows 10, Python 3.14 (`C:\Users\chent\AppData\Local\Python\pythoncore-3.14-64\python.exe`, PyYAML installed), Node 24, Git 2.52. No agent CLIs on PATH: the user runs desktop apps (Claude desktop, Codex app, Antigravity, Cursor, Copilot in the IDE; OpenCode config exists).

## Key files
- `handoff/SKILL.md` - the skill: when to write, how to write, template, resume workflow
- `handoff/scripts/snapshot.py` - inserts the auto-generated repo snapshot into HANDOFF.md
- `handoff/scripts/context_monitor.py` - Claude Code hook: context warnings and SessionStart pointer
- `install.py` - copies the skill into each tool's folder; `--hooks`, `--window`, `--rules`, `--uninstall`, `--dry-run`
- `README.md` - user documentation

## How to run and verify
- Preview an install without changing anything: `python install.py --hooks --rules --window 1000000 --dry-run`
- Snapshot: `python handoff/scripts/snapshot.py --print`
- Hook by hand: pipe `{"hook_event_name":"PostToolUse","session_id":"t","transcript_path":"<session .jsonl>"}` into `python handoff/scripts/context_monitor.py`
- Validate the skill: copy skill-creator's `quick_validate.py` to the scratchpad, then `python quick_validate.py handoff`

## Open questions for the user
- None.

<!-- handoff:snapshot:start -->
## Repo snapshot (auto-generated)

_Captured 2026-09-16 00:26 +0100 by `snapshot.py`. Compare with the live repo (`git status`) before continuing._

- **Root:** `C:\Users\chent\Desktop\Memory-Skill`
- **OS:** Windows 10
- **Branch:** `main` @ `5a775a8` - Add the handoff written while building this skill (2 minutes ago)
- **Upstream:** `origin/main` - ahead 0, behind 0
- **Remote:** https://github.com/chentaymane/Memory-Skill.git
- **Uncommitted:** 0 changed (1 file changed, 1 insertion(+), 1 deletion(-)), 0 untracked

**Recent commits**

```
5a775a8 2026-09-16 Add the handoff written while building this skill
76aa910 2026-09-16 Add handoff skill: cross-CLI HANDOFF.md for continuing work in any agent
```
<!-- handoff:snapshot:end -->
