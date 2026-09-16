# HANDOFF: handoff (chentaymane/handoff)

**Updated:** 2026-09-16 15:55 +0100 | **By:** Claude Code desktop / claude-opus-5 | **Status:** In progress

> **Next agent:** read this whole file, check it against the repo with `git status`, then continue from "Next steps". The "Auto handoff" section at the bottom is written by the handoff app itself, from this session's own log.

## Goal
A general tool, not a skill, that works across coding agents: when the context, the credit or the session is about to end, a handoff README (`HANDOFF.md`) must already exist in the work folder with what we want to do, where we stopped, and everything another agent needs. The user's words: "i wana a genral tool for most cli you can change the way and dont use skill we can do another way a app or somthing like that".

## Where we stopped
- Built `handoff` 1.0.0, a Python app with no dependencies (`handoff/` package; `python -m handoff`, or `pip install .` for a `handoff` command). README rewritten app-first.
- Verified on this machine: `status` reads the real logs (12 sessions in about a second); print-only handoffs rendered from a real Codex session (87% of its 30-day limit) and a real Claude session that hit its limit; background `start`/`stop` runs under pythonw; the Windows toast notification exits cleanly; the login item was tested only in a sandboxed APPDATA.
- Running the app on this repo found a bug: it matched its markers anywhere in the file, so this HANDOFF.md, which mentions them, got the auto section injected mid-sentence (pushed in `f86cf43`). Fixed: the markers only count on a line of their own. Added a regression test, applied the same fix to the skill's `snapshot.py`, and rebuilt this file. Temp files outside the project are no longer listed as changed files.
- Waiting on the user before: running the watcher permanently, `autostart on`, and removing the older skill hook from `~/.claude/settings.json`.

## Next steps
1. Ask the user: start the watcher now and turn on autostart? Remove the older skill hook (redundant now, about 0.3 s per tool call)?
2. Add readers for Cursor (SQLite `state.vscdb`, table `cursorDiskKV`, keys `composerData:*` and `bubbleId:*`), OpenCode (`~/.local/share/opencode/opencode.db`) and Gemini CLI (`~/.gemini/tmp/<hash>/chats/`), each with fixture tests.
3. If the user wants something visible, consider a tray icon or a small dashboard on top of `handoff status`.

## Decisions and constraints
- Read the agents' logs from outside instead of asking the agent: it keeps working after a session died of a credit limit, with no cooperation from the agent.
- Codex logs `rate_limits.primary` / `secondary` with `used_percent`, `window_minutes` and `resets_at` in its `token_count` events, so its usage-limit alerts are exact. Claude Code logs no percentage, only `rate_limit` API errors (`isApiErrorMessage`) once a limit is hit.
- The watcher only acts on logs modified after it started (it never backfills old projects), writes after 20 s of quiet, writes at once on alerts (usage 80/95%, context 70/85%, limit hit), and only for real work (a changed file, 3 commands or 2 requests).
- It owns only the section between the `<!-- handoff:auto:start -->` and `<!-- handoff:auto:end -->` marker lines; everything else in HANDOFF.md is kept. Writes are atomic (temp file then replace) and secrets are masked.
- It never writes into the home folder, a drive root, temp folders, agent settings folders, or a folder containing `.nohandoff`.
- The earlier skill, hook and installer moved to `extras/`; they are still installed on this machine from before.
- Pushing to this repo is pre-authorized by the user.

## Tried and failed / gotchas
- Finding markers with a plain substring search corrupts any file that quotes them. Match marker lines only (`^...$` with `re.M`).
- Antigravity stores conversations as binary `.pb` files (its `brain/` folder was empty here), so it can't be read yet.
- Local HTTP servers are blocked by the permission classifier. To preview HTML, put the file inside the project folder and open it with the browser tool.
- The skill-creator folder under `AppData\Roaming\Claude` is app-virtualized; copy its scripts to the scratchpad before running them.
- Under pythonw, git and PowerShell subprocesses need `CREATE_NO_WINDOW`, or console windows flash on screen.
- Deleted project folders still show up in `status`; `handoff now FOLDER --from LOG` rebuilds their handoff somewhere else.

## Key files
- `handoff/sources.py` - log readers for Claude Code and Codex, and log discovery
- `handoff/render.py` - builds and writes the auto section; git facts; secret masking
- `handoff/watch.py` - the polling loop, alert levels, where not to write
- `handoff/system.py` - notifications, background process, autostart, the `~/.handoff` files
- `handoff/cli.py` - `status`, `now`, `watch`, `start`, `stop`, `autostart`
- `tests/` - unittest tests with fixture logs
- `extras/` - the optional skill and its installer

## How to run and verify
- `python -m unittest discover -s tests -t .`
- `python -m handoff status`
- `python -m handoff now FOLDER --print` shows a handoff without writing it

## Open questions for the user
- Start the watcher now, and turn on autostart?
- Remove the older skill hook from `~/.claude/settings.json`?

<!-- handoff:auto:start -->
## Auto handoff

_Last update: 2026-09-16 15:48 +0100, from a **Claude Code** session (claude-opus-5). Kept current by the [handoff app](https://github.com/chentaymane/handoff): this section is rewritten automatically, anything outside it is kept._

### Goal
> i wana create a skill for all cli of coding agent like when the token has close to finish create a readme tell all about what we wana do and where we are stop and all information for other cli can use it

**Latest request:**

> bro i wana a genral tool for most cli you can change the way and dont use skill we can do another way a app or somthing like that

### Where we stopped
> Next is one sequential chain: re-run the tests after the `system.py` fix, let the app write its own section into this repo's `HANDOFF.md` from this live session, then commit and push.

### Next steps
1. Read "Where we stopped" and finish anything it left open.
2. Run `git status` to find uncommitted or half-finished edits before starting new work.

### Files changed in this session
- `handoff/scripts/snapshot.py` - written
- `install.py` - written
- `.gitignore` - written
- `assets/logo.svg` - written
- `handoff/scripts/context_monitor.py` - written
- `handoff/SKILL.md` - written
- `handoff/scripts/recover.py` - written
- `handoff/__init__.py` - written
- `handoff/__main__.py` - written
- `pyproject.toml` - written
- `tests/__init__.py` - written
- `tests/test_watch.py` - written
- `handoff/cli.py` - written
- `handoff/sources.py` - written
- `handoff/watch.py` - written
- `tests/test_sources.py` - written
- `README.md` - written
- `handoff/system.py` - written
- `handoff/render.py` - written
- `tests/test_render.py` - written
- `HANDOFF.md` - written

### Recent commands
- `python -m unittest discover -s tests -t . 2>&1 | tail -4`
- `cd /c/Users/chent/Desktop/Memory-Skill echo "=========== CLAUDE (Bus-Reminder, ended on a limit) ===========" python -m handoff now "C:/Users/chent/Desktop/B...`
- `cd /c/Users/chent/Desktop/Memory-Skill log=$(ls -t ~/.codex/sessions/*/*/*/*.jsonl | head -1) echo "=========== CODEX, lower half ===========" python -m hand...`
- `python -m unittest discover -s tests -t . 2>&1 | tail -4`
- `cd /c/Users/chent/Desktop/Memory-Skill S=/c/Users/chent/AppData/Local/Temp/claude/C--Users-chent-Desktop-Memory-Skill/ee766dbe-643b-4688-a2c7-9caa503084b1/sc...`
- `cd /c/Users/chent/Desktop/Memory-Skill python -m unittest discover -s tests -t . 2>&1 | tail -2 echo "=== the app writes its own section for this repo, from...`
- `python - <<'EOF' from pathlib import Path path = Path("extras/skills/handoff/scripts/snapshot.py") source = path.read_text(encoding="utf-8") old_find = ''' s...`
- `cd /c/Users/chent/Desktop/Memory-Skill python - <<'EOF' from pathlib import Path path = Path("extras/skills/handoff/scripts/snapshot.py") source = path.read_...`

### Errors seen
- Exit code 2 C:\Users\chent\AppData\Local\Python\pythoncore-3.14-64\python.exe: can't open file 'C:\\Users\\chent\\AppData\\Roaming\\Claude\\local-agent-mode-sessions\\skills-plugin\\dd7940b5-3675-4ed7-b0f7-8beb35c56567\\0f489140-6bd4-4e4...
- [navigate] opened file:///C:/Users/chent/AppData/Local/Temp/claude/C--Users-chent-Desktop-Memory-Skill/ee766dbe-643b-4688-a2c7-9caa503084b1/scratchpad/logo-preview.html in the preview pane (files outside the project folder render as stat...
- Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Expose Local Services]. If you have other tasks that don't depend on this action, continue working on those. IMPORTANT: You *may* attempt to accompli...

### Session
- **Tool:** Claude Code (claude-opus-5), 141 tool calls
- **Active:** 2026-09-15 23:45 to 2026-09-16 15:48
- **Context:** ~616K of 1000K tokens (62%, window size assumed)
- **Full log:** `C:\Users\chent\.claude\projects\C--Users-chent-Desktop-Memory-Skill\ee766dbe-643b-4688-a2c7-9caa503084b1.jsonl`

### Repo
- **Branch:** `main` @ `f86cf43` - Turn handoff into a standalone app that reads agents' session logs
- **Upstream:** `origin/main` - ahead 0, behind 0
- **Uncommitted:** 3 changed, 0 untracked

Recent commits:

```
f86cf43 2026-09-16 Turn handoff into a standalone app that reads agents' session logs
4783b92 2026-09-16 Cover credit limits, expired sessions and crashes
d30e308 2026-09-16 Add a logo and rewrite the README for GitHub
1ca1fe3 2026-09-16 Correct the pushed repo URL in the handoff (GitHub repo renamed to Save-Skill)
5a775a8 2026-09-16 Add the handoff written while building this skill
```

Working tree:

```
 M extras/skills/handoff/scripts/snapshot.py
 M handoff/render.py
 M tests/test_render.py
```
<!-- handoff:auto:end -->
