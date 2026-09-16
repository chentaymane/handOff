# HANDOFF: Cross-CLI "handoff" skill (repo: chentaymane/handoff)

**Updated:** 2026-09-16 01:05 +0100 | **By:** Claude Code desktop / claude-opus-5 | **Status:** Done

> **Next agent:** read this whole file, compare the Repo snapshot with the real repo (`git status`), then continue from "Next steps". Keep this file updated as you work.

## Goal
Build an Agent Skill that works in every coding agent (Claude Code, Codex, Gemini CLI / Antigravity, Cursor, Copilot, OpenCode, ...): when the context window or usage budget is nearly used up, the agent writes `HANDOFF.md` in the working folder (goal, where we stopped, next steps, decisions, failures, repo snapshot) so any other tool or a fresh session can continue. The user's words: "when the token has close to finish create a readme tell all about what we wana do and where we are stop and all information for other cli can use it". Done = skill + scripts + installer + README, tested, installed, and pushed.

## Where we stopped
Delivered and installed. Two rounds of work:

1. The skill itself, `snapshot.py`, the Claude Code hook, `install.py`, and the first README. Installed with `python install.py --hooks --rules` and pushed.
2. Answering "does it really cover credit limits and expired sessions?": the hook now also detects `rate_limit` errors and runs 30-minute checkpoints, `recover.py` rebuilds a handoff from a dead session's transcript, and the README was rebuilt with a logo, badges and a mermaid diagram.

Nothing is blocked. The only open item is the user's own live test in another tool.

## Next steps
1. **User's own live test:** open this folder in Codex (`$handoff`), Antigravity, Cursor or OpenCode and say "Read HANDOFF.md and continue".
2. If context warnings arrive too early in 1M-token sessions, re-run `python install.py --hooks --window 1000000` (the user chose Auto, which assumes 200K until usage passes it).
3. Optional, not done: full A/B eval with helper agents; package the skill as a shareable `.skill` file (`package_skill.py`, copy it to the scratchpad first - see gotchas).

## Done so far
- [x] `handoff/SKILL.md` - passes the skill-creator validator (description 968 chars, 116 lines). Covers writing, resuming and recovering.
- [x] `handoff/scripts/snapshot.py` - tested: repo with no commits, upstream ahead/behind, credential redaction, CRLF and UTF-16 files, non-git folder, run from a subfolder, idempotent.
- [x] `handoff/scripts/context_monitor.py` - 13 tests pass: context soft/urgent once per session, re-arm after `compact_boundary`, `rate_limit` credit alert (once, and skipped when HANDOFF.md is newer than the error), 30-minute checkpoints (refresh, first-file, quiet when Status is Done, quiet under 12 tool calls, `HANDOFF_CHECKPOINT_MIN=0` disables), sidechain and subagent events ignored, bad input exits 0.
- [x] `handoff/scripts/recover.py` - rebuilds a handoff from a transcript; verified against a real session that died on a credit limit (it flags that) and against this session.
- [x] `install.py` - tested in a fake home: dry run changes nothing, merges with existing hooks/env/CRLF files, idempotent, uninstall restores settings.json (JSON-equal) and CLAUDE.md (byte-identical).
- [x] `README.md` + `assets/logo.svg` - logo checked in a browser at 112/48/24px on light and dark, mermaid diagram verified to parse.
- [x] Installed on this machine (three skill folders, hook on three events, rule block in four instruction files) and pushed to https://github.com/chentaymane/handoff

## Decisions and constraints
- Output file is `HANDOFF.md` at the project root - the git top level, or the working folder outside git. Never a temp or home folder, never the project's README.md.
- Frontmatter uses only Agent Skills spec fields (`name`, `description`) so every tool accepts it.
- Skill folders: Claude Code reads only `~/.claude/skills`; Codex, Gemini CLI, Cursor, Copilot and OpenCode read `~/.agents/skills`; Antigravity (IDE, app, CLI) reads `~/.gemini/config/skills` and not `~/.agents/skills`.
- Only Claude Code gets automatic hooks: Codex hooks are experimental and unavailable on Windows; Gemini's `PreCompress` hook cannot prompt the model.
- Nothing warns the model before a credit limit or an expiry, so the cover is: 30-minute checkpoints, a `rate_limit` alert the moment a request fails, and `recover.py` afterwards.
- Hooks use exec form (`command` = absolute python.exe, `args` = [script path]). `additionalContext` is a plain string inside `hookSpecificOutput`.
- Context estimate = input + cache_creation + cache_read + output tokens of the last main-thread assistant entry. Default window 200K, switching to 1M above 200K. Env: `HANDOFF_CONTEXT_WINDOW`, `HANDOFF_SOFT_PCT` (60), `HANDOFF_URGENT_PCT` (75), `HANDOFF_CHECKPOINT_MIN` (30).
- The user's sessions really are 1M (a past session auto-compacted near 970K tokens), but they chose Auto.
- Pushing to this repo is pre-authorized by the user; installing, editing global config and spawning subagents still need asking.

## Tried and failed / gotchas
- WebFetch summaries of the Claude Code hooks docs were wrong (said `additionalContext` is an object). Trust the raw docs: https://code.claude.com/docs/en/hooks.md
- The skill-creator folder under `AppData\Roaming\Claude\...` is app-virtualized: Python cannot open its scripts from Git Bash or PowerShell. Read such a script and write a copy into the scratchpad, then run the copy.
- Local HTTP servers are blocked by the permission classifier ("Expose Local Services"). To preview HTML, put the file inside the project folder and open it with the browser tool - files outside it render as static snapshots only.
- Python start-up flags (`-S`, `-I`) do not make the hook faster (~330 ms per call here, almost all interpreter start-up).
- Machine: Windows 10, Python 3.14 (`C:\Users\chent\AppData\Local\Python\pythoncore-3.14-64\python.exe`, PyYAML installed), Node 24, Git 2.52. No agent CLIs on PATH; the user runs desktop apps.

## Key files
- `handoff/SKILL.md` - the skill: when to write, how to write, template, resume, recover
- `handoff/scripts/snapshot.py` - inserts the auto-generated repo snapshot into HANDOFF.md
- `handoff/scripts/context_monitor.py` - Claude Code hook: context, credit limits, checkpoints, session start
- `handoff/scripts/recover.py` - digest of a dead session, to rebuild a handoff from
- `install.py` - installer; `--hooks`, `--window`, `--rules`, `--uninstall`, `--dry-run`
- `README.md`, `assets/logo.svg` - documentation and logo

## How to run and verify
- Preview an install: `python install.py --hooks --rules --window 1000000 --dry-run`
- Snapshot: `python handoff/scripts/snapshot.py --print`
- Recover: `python handoff/scripts/recover.py --list` then `python handoff/scripts/recover.py`
- Hook by hand: pipe `{"hook_event_name":"PostToolUse","session_id":"t","transcript_path":"<session .jsonl>"}` into `python handoff/scripts/context_monitor.py`
- Validate the skill: copy skill-creator's `quick_validate.py` to the scratchpad, then `python quick_validate.py handoff`

## Open questions for the user
- None.

<!-- handoff:snapshot:start -->
## Repo snapshot (auto-generated)

_Captured 2026-09-16 01:01 +0100 by `snapshot.py`. Compare with the live repo (`git status`) before continuing._

- **Root:** `C:\Users\chent\Desktop\Memory-Skill`
- **OS:** Windows 10
- **Branch:** `main` @ `d30e308` - Add a logo and rewrite the README for GitHub (23 minutes ago)
- **Upstream:** `origin/main` - ahead 0, behind 0
- **Remote:** https://github.com/chentaymane/handoff.git
- **Uncommitted:** 3 changed (4 files changed, 290 insertions(+), 172 deletions(-)), 1 untracked

**Recent commits**

```
d30e308 2026-09-16 Add a logo and rewrite the README for GitHub
1ca1fe3 2026-09-16 Correct the pushed repo URL in the handoff (GitHub repo renamed to Save-Skill)
5a775a8 2026-09-16 Add the handoff written while building this skill
76aa910 2026-09-16 Add handoff skill: cross-CLI HANDOFF.md for continuing work in any agent
```

**Working tree** (`git status --short`)

```
 M README.md
 M handoff/SKILL.md
 M handoff/scripts/context_monitor.py
?? handoff/scripts/recover.py
```
<!-- handoff:snapshot:end -->
