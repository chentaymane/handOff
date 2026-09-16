# HANDOFF: handoff (chentaymane/handoff)

**Updated:** 2026-09-16 16:40 +0100 | **By:** Claude Code desktop / claude-opus-5 | **Status:** In progress

> **Next agent:** read this whole file, check it against the repo with `git status`, then continue from "Next steps". The "Auto handoff" section at the bottom is written by the handoff app itself, from this session's own log.

## Goal
A general tool, not a skill, that works across coding agents: when the context, the credit or the session is about to end, a handoff README (`HANDOFF.md`) must already exist in the work folder with what we want to do, where we stopped, and everything another agent needs. The user's words: "i wana a genral tool for most cli you can change the way and dont use skill we can do another way a app or somthing like that".

## Where we stopped
- `handoff` is a Python app with no dependencies that reads five agents' session data from disk: Claude Code, Codex, Cursor, OpenCode and Gemini CLI. `python -m handoff status | now | watch | start | stop | autostart`.
- Installed on the user's machine at their request: the watcher runs in the background and starts at login (`handoff autostart on`); the older skill's Claude Code hook was removed from `~/.claude/settings.json` (skill folders and rules kept).
- Verified on real data: Claude Code and Codex sessions; all 9 Cursor chats (database and agent transcripts, including one blocked by "You've hit your usage limit"); an OpenCode session with 51 tool calls. Gemini CLI is not installed here, so its reader is built from Gemini CLI's source and tested on sample logs only.
- 48 unit tests, with fixture logs and fixture SQLite databases for every agent.

## Next steps
1. The user's own live test: work in any project with any of the five agents, then open it in another agent and say "Read HANDOFF.md and continue".
2. When Gemini CLI is available, check its reader against a real `~/.gemini/tmp/*/chats` log and `~/.gemini/projects.json`.
3. Antigravity keeps conversations as binary `.pb` files; revisit if a readable export appears.
4. Optional: a tray icon or small dashboard on top of `handoff status`.

## Decisions and constraints
- Read the agents' data from outside instead of asking the agent: it keeps working after a session died of a credit limit.
- One reader per agent in `handoff/sources/`, each with `discover(max_age_hours) -> (ref, stamp)`, `read(ref) -> Session` and `folder(ref)`. A ref is a log path or `<database>#<session id>`; the stamp changes whenever the session does, which is all the watcher compares.
- Databases (Cursor `state.vscdb`, OpenCode `opencode.db`) are opened read-only through `file:///...?mode=ro` URIs, and only re-scanned when the file or its `-wal` changes.
- Cursor has two sources for the same chat ids: `~/.cursor/projects/<slug>/agent-transcripts/<chat>/<chat>.jsonl` (newer chats, plus `turn_ended` errors such as usage limits) and `composerData:` / `bubbleId:` rows (older chats, context tokens, todos). The slug is turned back into a folder by matching names on disk, because dashes are ambiguous.
- Only Codex logs a usage-limit percentage (`rate_limits.primary/secondary.used_percent`), so only Codex gets 80%/95% warnings; the others are caught when the limit is hit (Claude `rate_limit` errors, Cursor `turn_ended` errors, OpenCode HTTP 429, Gemini `RESOURCE_EXHAUSTED`).
- The watcher only acts on sessions active after it started, writes after 20 s of quiet, writes at once on alerts, only for real work, never in home, drive roots, temp or agent folders, and only inside its own marker lines.
- Pushing to this repo is pre-authorized by the user.

## Tried and failed / gotchas
- Markers found with a plain substring search corrupt any file that quotes them; match marker lines only.
- In Bash tool commands a doubled backslash can arrive as a single one, so an escaped tab written in a heredoc became a real tab and broke a Python file. Build such strings with chr(92).
- Tests for a reader must redirect every path that reader scans, or they pick up the real user's data (a Cursor test found the real transcripts).
- Some Cursor `composerData` values are NULL; `as_dict` turns them into `{}`.
- Local HTTP servers are blocked by the permission classifier; the skill-creator folder under AppData/Roaming/Claude is app-virtualized; git and PowerShell under pythonw need `CREATE_NO_WINDOW`.

## Key files
- `handoff/session.py` - the Session shape and the helpers every reader shares
- `handoff/sources/` - `claude.py`, `codex.py`, `cursor.py`, `opencode.py`, `gemini.py`, `_db.py`, and the registry in `__init__.py`
- `handoff/render.py` - builds and writes the auto section; git facts; secret masking
- `handoff/watch.py` - the polling loop, alert levels, where not to write
- `handoff/system.py` - notifications, background process, autostart, the `~/.handoff` files
- `handoff/cli.py` - the commands
- `tests/` - 48 tests; `extras/` - the optional skill and its installer

## How to run and verify
- `python -m unittest discover -s tests -t .`
- `python -m handoff status --days 30`
- `python -m handoff now FOLDER --print` shows a handoff without writing it

## Open questions for the user
- None.

<!-- handoff:auto:start -->
## Auto handoff

_Last update: 2026-09-16 16:31 +0100, from a **Claude Code** session (claude-opus-5). Kept current by the [handoff app](https://github.com/chentaymane/handoff): this section is rewritten automatically, anything outside it is kept._

**Heads-up:** the context window is 77% full.

### Goal
> i wana create a skill for all cli of coding agent like when the token has close to finish create a readme tell all about what we wana do and where we are stop and all information for other cli can use it

**Latest request:**

> bro i wana a genral tool for most cli you can change the way and dont use skill we can do another way a app or somthing like that

### Where we stopped
> Everything is written except the new tests for the three new readers and the watcher-test patch, and the old single-file `sources.py` still needs deleting. Those three are independent:

### Next steps
1. Read "Where we stopped" and finish anything it left open.
2. Run `git status` to find uncommitted or half-finished edits before starting new work.

### Files changed in this session
_The last 25 of 30 files:_
- `handoff/SKILL.md` - written
- `handoff/scripts/recover.py` - written
- `handoff/__init__.py` - written
- `handoff/__main__.py` - written
- `pyproject.toml` - written
- `tests/__init__.py` - written
- `handoff/sources.py` - written
- `handoff/system.py` - written
- `tests/test_render.py` - written
- `handoff/session.py` - written
- `handoff/sources/_db.py` - written
- `handoff/sources/claude.py` - written
- `handoff/sources/codex.py` - written
- `handoff/sources/gemini.py` - written
- `handoff/sources/opencode.py` - written
- `handoff/watch.py` - written
- `handoff/cli.py` - written
- `handoff/render.py` - written
- `tests/test_sources.py` - written
- `tests/test_watch.py` - written
- `handoff/sources/cursor.py` - written
- `handoff/sources/__init__.py` - written
- `tests/test_more_sources.py` - written
- `README.md` - written
- `HANDOFF.md` - written

### Recent commands
- `python -m unittest discover -s tests -t . 2>&1 | tail -15`
- `cd /c/Users/chent/Desktop/Memory-Skill echo "=== status over 120 days (read-only)"; t0=$(date +%s%N) python -m handoff status --days 120 --limit 40 | grep -E...`
- `export PYTHONIOENCODING=utf-8 echo "== agent-transcripts folders and files" for d in ~/.cursor/projects/c-Users-chent-Desktop-Insta-auto/agent-transcripts/*/...`
- `export PYTHONIOENCODING=utf-8 python - <<'EOF' import collections, glob, json, os files = sorted(glob.glob(os.path.expanduser("~/.cursor/projects/*/agent-tra...`
- `python -m unittest discover -s tests -t . 2>&1 | tail -12`
- `export PYTHONIOENCODING=utf-8 && python - <<'EOF' import datetime from handoff import sources from handoff.sources import cursor items = sorted(cursor.discov...`
- `python -m unittest discover -s tests -t . 2>&1 | tail -4 && python -m handoff stop`
- `cd /c/Users/chent/Desktop/Memory-Skill python -c "import sys; open('HANDOFF.md', 'w', encoding='utf-8', newline='').write(sys.stdin.read())" <<'EOF' # HANDOF...`

### Errors seen
- [navigate] opened file:///C:/Users/chent/AppData/Local/Temp/claude/C--Users-chent-Desktop-Memory-Skill/ee766dbe-643b-4688-a2c7-9caa503084b1/scratchpad/logo-preview.html in the preview pane (files outside the project folder render as stat...
- Permission for this action was denied by the Claude Code auto mode classifier. Reason: [Expose Local Services]. If you have other tasks that don't depend on this action, continue working on those. IMPORTANT: You *may* attempt to accompli...
- Exit code 1 === status over 120 days (read-only) Reads: Claude Code, Codex, Gemini CLI, Cursor, OpenCode LAST ACTIVE TOOL CONTEXT USAGE LIMIT HANDOFF.md FOLDER (took 2537 ms) === newest real Cursor and OpenCode sessions, rendered but not...
- Exit code 1 == agent-transcripts folders and files -- /c/Users/chent/.cursor/projects/c-Users-chent-Desktop-Insta-auto/agent-transcripts/5ab487ef-8544-4be6-9c85-b9a642aca251/ -rw-r--r-- 1 chent 197609 139 Jul 20 00:37 5ab487ef-8544-4be6-...
- <tool_use_error>File has been modified since read, either by the user or by a linter. Read it again before attempting to write it.</tool_use_error>

### Session
- **Tool:** Claude Code (claude-opus-5), 182 tool calls
- **Active:** 2026-09-15 23:45 to 2026-09-16 16:31
- **Context:** ~773K of 1000K tokens (77%, window size assumed)
- **Full log:** `C:\Users\chent\.claude\projects\C--Users-chent-Desktop-Memory-Skill\ee766dbe-643b-4688-a2c7-9caa503084b1.jsonl`

### Repo
- **Branch:** `main` @ `a50d391` - Fix marker matching that corrupted HANDOFF.md files quoting the markers
- **Upstream:** `origin/main` - ahead 0, behind 0
- **Uncommitted:** 7 changed, 3 untracked

Recent commits:

```
a50d391 2026-09-16 Fix marker matching that corrupted HANDOFF.md files quoting the markers
f86cf43 2026-09-16 Turn handoff into a standalone app that reads agents' session logs
4783b92 2026-09-16 Cover credit limits, expired sessions and crashes
d30e308 2026-09-16 Add a logo and rewrite the README for GitHub
1ca1fe3 2026-09-16 Correct the pushed repo URL in the handoff (GitHub repo renamed to Save-Skill)
```

Working tree:

```
 M README.md
 M handoff/cli.py
 M handoff/render.py
D  handoff/sources.py
 M handoff/watch.py
 M tests/test_sources.py
 M tests/test_watch.py
?? handoff/session.py
?? handoff/sources/
?? tests/test_more_sources.py
```
<!-- handoff:auto:end -->
