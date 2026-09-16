"""The background loop: notice agent activity and keep each folder's HANDOFF.md current."""

import os
import tempfile
import time
from pathlib import Path

from . import render, sources, system

POLL_SECONDS = 5
QUIET_SECONDS = 20       # a log quiet this long means the agent finished a step: write the handoff
REPARSE_SECONDS = 15     # while an agent is busy, re-read its log at most this often to catch alerts
LOOKBACK_HOURS = 48
LIMIT_LEVELS = (80, 95)
CONTEXT_LEVELS = (70, 85)
AGENT_DIRS = render.AGENT_DIRS
TEMP_DIR = None          # overridden in tests


def skip_reason(session, root):
    """Why the watcher should not write a HANDOFF.md for this session, or None if it should."""
    try:
        root = Path(root).resolve()
    except OSError:
        return "folder unavailable"
    if not root.is_dir():
        return "folder no longer exists"
    home = Path.home().resolve()
    if root == home or root == Path(root.anchor):
        return "home folder or drive root"
    temp = Path(TEMP_DIR or tempfile.gettempdir()).resolve()
    if root == temp or temp in root.parents:
        return "temporary folder"
    if any(home / name == root or home / name in root.parents for name in AGENT_DIRS):
        return "agent settings folder"
    if (root / ".nohandoff").exists():
        return ".nohandoff file"
    if not (session.files or len(session.commands) >= 3 or len(session.asks) >= 2 or session.limit_hit):
        return "too little activity yet"
    return None


def alerts(session):
    """(key, title) for every alert level this session has reached."""
    found = []
    if session.limit_hit:
        found.append(("limit-hit", f"{session.tool} hit its usage limit"))
    elif session.limit_percent is not None:
        level = max((level for level in LIMIT_LEVELS if session.limit_percent >= level), default=None)
        if level:
            found.append((f"limit-{level}", f"{session.tool}: {session.limit_percent:.0f}% of the usage limit used"))
    percent, _ = render.context_percent(session)
    if percent is not None:
        level = max((level for level in CONTEXT_LEVELS if percent >= level), default=None)
        if level:
            found.append((f"context-{level}", f"{session.tool}: context {percent}% full"))
    return found


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


class Watcher:
    def __init__(self, echo=print):
        self.echo = echo
        self.started = time.time()
        self.seen = {}
        state = system.load_json(system.STATE_FILE, {})
        cutoff = time.time() - 30 * 86400
        self.fired = {path: keys for path, keys in (state.get("alerts") or {}).items() if _mtime(path) >= cutoff}

    def say(self, message):
        system.log(message)
        self.echo(message)

    def run(self):
        other = system.watcher_pid()
        if other and other != os.getpid():
            self.say(f"another watcher is already running (pid {other})")
            return 1
        system.write_pid()
        self.say(f"watching Claude Code and Codex sessions (pid {os.getpid()}), press Ctrl+C to stop")
        try:
            while True:
                try:
                    self.tick()
                except Exception as exc:  # one bad log must never stop the watcher
                    self.say(f"error: {exc!r}")
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            self.say("stopped")
        finally:
            system.clear_pid()
        return 0

    def tick(self, now=None):
        now = time.time() if now is None else now
        for tool, path, mtime in sources.transcripts(LOOKBACK_HOURS):
            if mtime < self.started:
                break  # newest first, so everything from here on predates the watcher
            try:
                size = path.stat().st_size
            except OSError:
                continue
            seen = self.seen.setdefault(str(path), {"size": -1, "mtime": 0.0, "parsed": 0.0, "dirty": False})
            if (seen["size"], seen["mtime"]) != (size, mtime):
                seen.update(size=size, mtime=mtime, dirty=True)
                if now - seen["parsed"] >= REPARSE_SECONDS:
                    self.process(tool, path, seen, now, final=False)
            elif seen["dirty"] and now - mtime >= QUIET_SECONDS:
                self.process(tool, path, seen, now, final=True)

    def process(self, tool, path, seen, now, final):
        seen["parsed"] = now
        session = sources.read_session(tool, path)
        if not session or not session.cwd:
            seen["dirty"] = False
            return
        fired = set(self.fired.get(str(path), []))
        fresh = [(key, title) for key, title in alerts(session) if key not in fired]
        if not final and not fresh:
            return  # still busy and nothing urgent: wait until it goes quiet
        if final:
            seen["dirty"] = False
        root = render.project_root(session.cwd)
        handoff = root / render.HANDOFF_NAME
        reason = skip_reason(session, root)
        if reason is None:
            try:
                if render.write_handoff(root, render.build_section(session, root)):
                    self.say(f"updated {handoff} ({session.tool})")
            except OSError as exc:
                reason = f"could not write it: {exc}"
                self.say(f"{handoff}: {reason}")
        for key, title in fresh:
            body = (f"HANDOFF.md is up to date in {root.name}." if reason is None
                    else f"No HANDOFF.md written for {root.name} ({reason}).")
            system.notify(title, body)
            self.say(f"alert: {title} - {body}")
            fired.add(key)
        if fresh:
            self.fired[str(path)] = sorted(fired)
            system.save_json(system.STATE_FILE, {"alerts": self.fired})
