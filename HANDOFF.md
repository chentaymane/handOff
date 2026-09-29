# HANDOFF: handoff (chentaymane/handoff)

**Updated:** 2026-09-29 | **By:** Claude Code (Linux) / claude-opus-5-5 | **Status:** Working, committed and pushed

> **Next agent:** read this whole file, check it against the repo with `git status`, then continue from "Next steps". The "Auto handoff" section at the bottom is written by the handoff app itself, from this session's own log.

## Goal
A general app, not a skill, that works across the popular coding CLIs: when the context, the credit, the session limit or anything else is about to end a session, a `HANDOFF.md` must already exist in the project with what we want to do, where we stopped, and everything another agent needs to continue. The user's words: "i wanna don't be skill, i need it to be a app work with the most popular cli coding".

## Where we stopped
- Moved to Linux (Ubuntu, GNOME, Python 3.12). The app is installed there with `python3 -m handoff install`: launcher `~/.local/bin/handoff`, autostart `~/.config/autostart/handoff-watch.desktop`, watcher running. Verified live: it wrote this file and sent a notify-send alert within 5 s.
- Reads 9 agents: Claude Code, Codex, Cursor, Gemini CLI, OpenCode, plus new **Qwen Code**, **GitHub Copilot CLI**, **Freebuff/Codebuff** and **Aider** (built from their source and published formats, tested on sample logs only; none are installed here). Freebuff's reader follows its source (CodebuffAI/freebuff: `cli/src/project-files.ts`, `utils/run-state-storage.ts`, `types/chat.ts`): the data folder keeps only the project's name, so the real folder comes from `run-state.json` `fileContext.cwd`, and edits are often made by spawned agents, so nested `agent` blocks are read too.
- Claude Code reader: strips `<ide_*>` and `<system-reminder>` tags from requests, skips `<synthetic>` placeholders ("No response requested."), reads `ai-title` / `custom-title` and the `away_summary` recap, detects newer limit messages ("You've hit your limit"), 1M window for `[1m]` models.
- Render: files changed now include files from commits made since the session started (agents that edit through shell commands showed 2 files instead of 51); "Commits made during this session" in Repo.
- New `handoff install` / `handoff uninstall`; `pip install .` is blocked on Ubuntu 24.04 (PEP 668). Fixed pyproject, which left `handoff.sources` out of the package. Version 1.1.0.
- Removed `extras/` (the optional skill and its installer): the user wants an app, not a skill.
- Local web dashboard: `handoff dashboard` (`handoff/dashboard.py` + `dashboard.html`, stdlib `ThreadingHTTPServer` on 127.0.0.1:7788). Host header must be 127.0.0.1/localhost, POSTs need `X-Handoff: 1` and a JSON body (blocks other websites), and only folders from the sessions overview can be read or written. Checked in Chrome with real data.
- Shared logic moved to `handoff/app.py` (overview, find_session, write_now); `watch.place_reason` is the one rule for folders that never get a HANDOFF.md.
- 64 unit tests pass.

## Next steps
1. When Qwen Code, Copilot CLI, Freebuff, Aider or Gemini CLI get used for real, check each reader against a real log.
2. Claude Code's context window is guessed (200K unless a model ends in `[1m]` or tokens pass 200K); the social-network session showed "100% of 200K" while still running uncompacted, so the real window may be 1M. This session passed 200K without compacting too, which confirms 1M for claude-opus-5-5 here.
3. Optional: more agents (Crush, Amp, Kilo Code, Factory Droid); Antigravity still stores binary `.pb` files.

## Decisions and constraints
- No skill, no hook, no prompt: read the agents' data from outside instead of asking the agent, so it keeps working after a session died of a credit limit.
- One reader per agent in `handoff/sources/`, each with `discover(max_age_hours) -> (ref, stamp)`, `read(ref) -> Session` and `folder(ref)`. A ref is a log path or `<database>#<session id>`; the stamp changes whenever the session does, which is all the watcher compares.
- Databases (Cursor `state.vscdb`, OpenCode `opencode.db`) are opened read-only through `file:///...?mode=ro` URIs, and only re-scanned when the file or its `-wal` changes.
- Cursor has two sources for the same chat ids: `~/.cursor/projects/<slug>/agent-transcripts/<chat>/<chat>.jsonl` (newer chats, plus `turn_ended` errors such as usage limits) and `composerData:` / `bubbleId:` rows (older chats, context tokens, todos). The slug is turned back into a folder by matching names on disk, because dashes are ambiguous.
- Aider has no central log: its `.aider.chat.history.md` is found by scanning 1-2 levels under home and usual code folders (or `HANDOFF_SCAN`), cached for 60 s.
- Only Codex logs a usage-limit percentage (`rate_limits.primary/secondary.used_percent`), so only Codex gets 80%/95% warnings; the others are caught when the limit is hit (Claude `rate_limit` errors, Cursor `turn_ended` errors, OpenCode HTTP 429, Gemini `RESOURCE_EXHAUSTED`).
- The watcher only acts on sessions active after it started, writes after 20 s of quiet, writes at once on alerts, only for real work, never in home, drive roots, temp or agent folders, and only inside its own marker lines.

## Tried and failed / gotchas
- Markers found with a plain substring search corrupt any file that quotes them; match marker lines only.
- In Bash tool commands a doubled backslash can arrive as a single one, so an escaped tab written in a heredoc became a real tab and broke a Python file. Build such strings with chr(92).
- Tests for a reader must redirect every path that reader scans, or they pick up the real user's data (a Cursor test found the real transcripts).
- Some Cursor `composerData` values are NULL; `as_dict` turns them into `{}`.
- Local HTTP servers are blocked by the permission classifier; the skill-creator folder under AppData/Roaming/Claude is app-virtualized; git and PowerShell under pythonw need `CREATE_NO_WINDOW`.

## Key files
- `handoff/session.py` - the Session shape and the helpers every reader shares
- `handoff/sources/` - `claude.py`, `codex.py`, `cursor.py`, `opencode.py`, `gemini.py`, `qwen.py`, `copilot.py`, `codebuff.py`, `aider.py`, `_db.py`, and the registry in `__init__.py`
- `handoff/render.py` - builds and writes the auto section; git facts; secret masking
- `handoff/watch.py` - the polling loop, alert levels, where not to write
- `handoff/system.py` - notifications, background process, autostart, the `handoff` launcher, the `~/.handoff` files
- `handoff/cli.py` - the commands
- `handoff/app.py` - what the CLI and the dashboard share
- `handoff/dashboard.py`, `handoff/dashboard.html` - the local web dashboard
- `tests/` - 64 tests

## How to run and verify
- `python -m unittest discover -s tests -t .`
- `python -m handoff status --days 30`
- `python -m handoff now FOLDER --print` shows a handoff without writing it
- `python -m handoff dashboard` opens the dashboard

## Open questions for the user
- None.

<!-- handoff:auto:start -->
## Auto handoff

_Last update: 2026-09-29 16:50 +0000, from a **Claude Code** session (claude-opus-5-5). Kept current by the [handoff app](https://github.com/chentaymane/handoff): this section is rewritten automatically, anything outside it is kept._

**Heads-up:** the context window is 95% full.

### Goal
**Session:** App fix effort

> can you fix this app  i need it /effort

**Latest request:**

> tell me all the cli now he support them and we can add a dashbor for stub run inside a web localy and commit all that and pushit

### Where we stopped
> Now the dashboard server. It uses only the Python standard library, only listens on this computer (127.0.0.1), and rejects requests from other websites.

### Next steps
1. Read "Where we stopped" and finish anything it left open.
2. Run `git status` to find uncommitted or half-finished edits before starting new work.

### Files changed in this session
- `handoff/sources/qwen.py` - written
- `handoff/sources/copilot.py` - written
- `handoff/sources/aider.py` - written
- `tests/test_new_sources.py` - written
- `handoff/sources/codebuff.py` - written
- `handoff/app.py` - written
- `handoff/dashboard.py` - written

### Recent commands
- `cd /tmp/claude-71182/-home-achent-Desktop-handOff/c0e32e13-2741-4979-a7e6-028400e91c41/scratchpad/fb && grep -rn "projectRoot\b\|cwd:" sdk/src/run-state.ts c...`
- `cd /tmp/claude-71182/-home-achent-Desktop-handOff/c0e32e13-2741-4979-a7e6-028400e91c41/scratchpad/fb && sed -n 58,68p common/src/util/file.ts; grep -rn "file...`
- `cd /tmp/claude-71182/-home-achent-Desktop-handOff/c0e32e13-2741-4979-a7e6-028400e91c41/scratchpad/fb && grep -rn "timestamp: " cli/src/utils/message-history....`
- `python3 - <<'EOF' p='handoff/sources/codebuff.py'; s=open(p).read() old=''' text = text_of(output) if not isinstance(output, str) else output if isinstance(o...`
- `python3 - <<'EOF' p='tests/test_new_sources.py'; s=open(p).read() s=s.replace("from handoff.sources import aider, claude, copilot, qwen","from handoff.source...`
- `python3 - <<'EOF' import re p='README.md'; s=open(p).read() s=s.replace("OpenCode, Qwen Code, GitHub Copilot CLI and Aider) and keeps","OpenCode, Qwen Code,...`
- `git remote -v && git status -sb | head -3 && python3 -c " import time from handoff import sources t=time.time() for tool, ref, stamp in sources.transcripts(7...`
- `python3 - <<'EOF' p='handoff/cli.py'; s=open(p).read() start=s.index("def age(path):"); end=s.index("def cmd_now(args):") s=s[:start]+'''def cmd_status(args)...`

### Errors seen
- Exit code 1 Python 3.12.3 ................................................ ---------------------------------------------------------------------- Ran 48 tests in 0.113s OK (eval):1: == not found
- Exit code 1 Watcher: not running - start it with: handoff start Autostart: off - turn it on with: handoff autostart on Reads: Claude Code, Codex, Gemini CLI, Cursor, OpenCode Log file: /home/achent/.handoff/handoff.log LAST ACTIVE TOOL C...
- Exit code 1 import os from 'os' import path from 'path' import { env } from '@codebuff/common/env' import { getCliEnv } from './env' /** * Resolve the on-disk config directory for the CLI. * * Lives in its own module (depending only on '...

### Session
- **Tool:** Claude Code (claude-opus-5-5), 75 tool calls
- **Active:** 2026-09-29 16:09 to 2026-09-29 16:50
- **Context:** ~189K of 200K tokens (95%, window size assumed)
- **Full log:** `/home/achent/.claude/projects/-home-achent-Desktop-handOff/c0e32e13-2741-4979-a7e6-028400e91c41.jsonl`

### Repo
- **Branch:** `main` @ `b4d248e` - Fix the wording of handoff start's message
- **Upstream:** `origin/main` - ahead 0, behind 0
- **Uncommitted:** 14 changed, 7 untracked

Recent commits:

```
b4d248e 2026-09-16 Fix the wording of handoff start's message
cd801a2 2026-09-16 Read Cursor, OpenCode and Gemini CLI sessions too
a50d391 2026-09-16 Fix marker matching that corrupted HANDOFF.md files quoting the markers
f86cf43 2026-09-16 Turn handoff into a standalone app that reads agents' session logs
4783b92 2026-09-16 Cover credit limits, expired sessions and crashes
```

Working tree:

```
 M README.md
D  extras/install_skill.py
D  extras/skills/handoff/SKILL.md
D  extras/skills/handoff/scripts/context_monitor.py
D  extras/skills/handoff/scripts/recover.py
D  extras/skills/handoff/scripts/snapshot.py
 M handoff/__init__.py
 M handoff/cli.py
 M handoff/render.py
 M handoff/session.py
 M handoff/sources/__init__.py
 M handoff/sources/claude.py
 M handoff/system.py
 M pyproject.toml
?? handoff/app.py
?? handoff/dashboard.py
?? handoff/sources/aider.py
?? handoff/sources/codebuff.py
?? handoff/sources/copilot.py
?? handoff/sources/qwen.py
... and 1 more
```
<!-- handoff:auto:end -->
