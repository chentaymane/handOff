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
- README rewritten: dashboard screenshot, supported-CLI table with tested status, HANDOFF.md contents, privacy, configuration, FAQ, how to add a CLI. Dashboard shows paths under home as `~/...`.

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
- 2026-09-29 16:57 the user ran `handoff uninstall` on this PC themselves: the watcher, autostart and `~/.local/bin/handoff` are gone on purpose. Don't reinstall unless asked.
- README screenshot (`assets/dashboard.png`) uses demo data: a fake HOME with sample sessions for four CLIs, and TMPDIR moved elsewhere, because folders under /tmp count as temporary and get no HANDOFF.md. Never screenshot the user's real sessions for the repo.
- `pkill -f PATTERN` also kills the Bash tool's own shell when PATTERN appears in the command; use `pgrep` and kill the pid.
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

_Last update: 2026-09-29 16:56 +0000, from a **Claude Code** session (claude-opus-5-5). Kept current by the [handoff app](https://github.com/chentaymane/handoff): this section is rewritten automatically, anything outside it is kept._

### Goal
**Session:** App fix effort

> can you fix this app  i need it /effort

**Latest request:**

> push

### Where we stopped
> The push failed again: this PC still isn't logged in to GitHub, and I can't sign in for you. Run these in the prompt, with the `!` in front:
>
> ```
> ! gh auth login
> ! gh auth setup-git
> ```
>
> In `gh auth login`, choose **GitHub.com**, then **HTTPS**, then **Login with a web browser**, and finish the sign-in in the browser it opens. Then say "push" again and I'll push the commit, which is still waiting.
>
> `HANDOFF.md` shows as changed again because the watcher keeps its auto-section current while we work. I can include that in the push too.

### Next steps
1. Read "Where we stopped" and finish anything it left open.
2. Run `git status` to find uncommitted or half-finished edits before starting new work.

### Files changed in this session
- `HANDOFF.md` - edited
- `README.md` - edited
- `extras/install_skill.py` - deleted
- `extras/skills/handoff/SKILL.md` - deleted
- `extras/skills/handoff/scripts/context_monitor.py` - deleted
- `extras/skills/handoff/scripts/recover.py` - deleted
- `extras/skills/handoff/scripts/snapshot.py` - deleted
- `handoff/__init__.py` - edited
- `handoff/cli.py` - edited
- `handoff/render.py` - edited
- `handoff/session.py` - edited
- `handoff/sources/__init__.py` - edited
- `handoff/sources/claude.py` - edited
- `handoff/system.py` - edited
- `handoff/watch.py` - edited
- `pyproject.toml` - edited
- `handoff/sources/qwen.py` - written
- `handoff/sources/copilot.py` - written
- `handoff/sources/aider.py` - written
- `tests/test_new_sources.py` - written
- `handoff/sources/codebuff.py` - written
- `handoff/app.py` - written
- `handoff/dashboard.py` - written
- `handoff/dashboard.html` - written
- `tests/test_dashboard.py` - written

### Recent commands
- `python3 -m unittest discover -s tests -t . 2>&1 | tail -2`
- `python3 -m handoff dashboard --no-open`
- `pid=$(pgrep -f "m handoff dashboard" | head -1); [ -n "$pid" ] && kill $pid; echo stopped $pid`
- `python3 - <<'EOF' p='README.md'; s=open(p).read() def rep(a,b): global s assert a in s, a[:70]; s=s.replace(a,b) rep('''| 'handoff install' / 'handoff uninst...`
- `git diff --cached | grep -niE "gmail|password|token=[redacted]" | head; python3 -m unittest discover -s tests -t . 2>&1 | tail -1`
- `git commit -q -F - <<'EOF' Add a local dashboard and read Qwen Code, Copilot CLI, Freebuff and Aider - handoff dashboard: a local web page (127.0.0.1 only) w...`
- `which gh && gh auth status 2>&1 | head -5; ls ~/.ssh 2>/dev/null; git config --get credential.helper`
- `gh auth status 2>&1 | head -3; git status -sb | head -3; git push origin main 2>&1 | tail -3`

### Errors seen
- Exit code 1 Python 3.12.3 ................................................ ---------------------------------------------------------------------- Ran 48 tests in 0.113s OK (eval):1: == not found
- Exit code 1 Watcher: not running - start it with: handoff start Autostart: off - turn it on with: handoff autostart on Reads: Claude Code, Codex, Gemini CLI, Cursor, OpenCode Log file: /home/achent/.handoff/handoff.log LAST ACTIVE TOOL C...
- Exit code 1 import os from 'os' import path from 'path' import { env } from '@codebuff/common/env' import { getCliEnv } from './env' /** * Resolve the on-disk config directory for the CLI. * * Lives in its own module (depending only on '...
- Exit code 144
- Exit code 1 /usr/bin/gh You are not logged into any GitHub hosts. To log in, run: gh auth login

### Session
- **Tool:** Claude Code (claude-opus-5-5), 98 tool calls
- **Active:** 2026-09-29 16:09 to 2026-09-29 16:56
- **Context:** ~219K of 1000K tokens (22%, window size assumed)
- **Full log:** `/home/achent/.claude/projects/-home-achent-Desktop-handOff/c0e32e13-2741-4979-a7e6-028400e91c41.jsonl`

### Repo
- **Branch:** `main` @ `0819762` - Add a local dashboard and read Qwen Code, Copilot CLI, Freebuff and Aider
- **Upstream:** `origin/main` - ahead 1, behind 0
- **Uncommitted:** 0 changed, 0 untracked

Commits made during this session:

```
0819762 09-29 16:53 Add a local dashboard and read Qwen Code, Copilot CLI, Freebuff and Aider
```
<!-- handoff:auto:end -->
