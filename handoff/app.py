"""What the command line and the dashboard share: the sessions overview, and writing a handoff on demand."""

import os
import time
from pathlib import Path

from . import render, sources, system
from .watch import alerts, place_reason

_cache = {}  # ref -> (stamp, Session): sessions are only re-read when their log changes


def age_text(seconds):
    if seconds is None:
        return "none"
    if seconds < 3600:
        return f"{int(seconds // 60)} min old"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h old"
    return f"{int(seconds // 86400)} d old"


def file_age(path):
    try:
        return max(0.0, time.time() - Path(path).stat().st_mtime)
    except OSError:
        return None


def find_session(root, days=60):
    """The newest session, from any agent, whose working folder is `root` or inside it."""
    base = os.path.normcase(str(root)).rstrip("\\/")
    for tool, ref, _ in sources.transcripts(days * 24):
        cwd = sources.session_cwd(tool, ref)
        if not cwd:
            continue
        folder = os.path.normcase(os.path.abspath(cwd)).rstrip("\\/")
        if folder == base or folder.startswith(base + os.sep):
            return tool, ref
    return None


def cached_session(tool, ref, stamp):
    hit = _cache.get(ref)
    if hit and hit[0] == stamp:
        return hit[1]
    session = sources.read_session(tool, ref)
    _cache[ref] = (stamp, session)
    return session


def overview(days=7, limit=12):
    """The latest sessions, newest first, as plain dicts."""
    rows = []
    for tool, ref, stamp in sources.transcripts(days * 24)[:limit]:
        session = cached_session(tool, ref, stamp)
        if not session or not session.cwd:
            continue
        root = render.project_root(session.cwd)
        percent, window = render.context_percent(session)
        handoff = root / render.HANDOFF_NAME
        rows.append({
            "tool": session.tool,
            "source": tool,
            "ref": str(ref),
            "folder": str(root),
            "name": root.name,
            "active": stamp,
            "model": session.model,
            "title": session.title,
            "goal": render.one_line(session.asks[0], 240) if session.asks else "",
            "latest": render.one_line(session.asks[-1], 240) if len(session.asks) > 1 else "",
            "last_reply": render.one_line(session.agent_last, 400),
            "context_percent": percent,
            "context_tokens": session.context_tokens,
            "context_window": window,
            "window_assumed": percent is not None and not session.context_window,
            "limit_percent": session.limit_percent,
            "limit_window": session.limit_window,
            "limit_hit": session.limit_hit,
            "alerts": [title for _, title in alerts(session)],
            "handoff_age": file_age(handoff),
            "blocked": place_reason(root),  # why no HANDOFF.md is written here, if it never is
            "files": len(session.files),
            "tool_calls": session.tool_calls,
        })
    return rows


def watcher_state():
    return {"pid": system.watcher_pid(), "autostart": system.autostart_path().exists(),
            "log": str(system.LOG_FILE)}


def write_now(folder):
    """Write HANDOFF.md in `folder` from its latest session. Returns (ok, message)."""
    folder = Path(folder).resolve()
    if not folder.is_dir():
        return False, f"Not a folder: {folder}"
    root = render.project_root(folder)
    reason = place_reason(root)
    if reason:
        return False, f"Not writing into {root} ({reason})."
    found = find_session(root)
    if not found:
        return False, f"No agent session found for {root}."
    session = sources.read_session(*found)
    if not session:
        return False, f"Could not read {found[1]}."
    changed = render.write_handoff(root, render.build_section(session, root))
    return True, (f"{'Wrote' if changed else 'Already up to date:'} {root / render.HANDOFF_NAME} "
                  f"(from {session.tool})")
