"""Every agent the app can read, behind one small interface.

Each source module has NAME, LABEL and three functions:

    discover(max_age_hours)  -> (ref, stamp) for each session; stamp changes whenever the session does
    read(ref)                -> Session
    folder(ref)              -> the session's working folder, found cheaply

A ref is a log file path, or "<database>#<session id>" for agents that keep their chats in SQLite.
"""

import time
from pathlib import Path

from ..session import Session, window_label  # noqa: F401 - re-exported for callers and tests
from . import claude, codex, cursor, gemini, opencode

MODULES = {module.NAME: module for module in (claude, codex, gemini, cursor, opencode)}
LABELS = ", ".join(module.LABEL for module in MODULES.values())


def transcripts(max_age_hours=None):
    """Every known session as (tool, ref, stamp), newest first."""
    cutoff = time.time() - max_age_hours * 3600 if max_age_hours else 0
    found = []
    for name, module in list(MODULES.items()):
        try:
            found += [(name, ref, stamp) for ref, stamp in module.discover(max_age_hours) if stamp >= cutoff]
        except Exception:  # one agent's unreadable data must not hide the others
            continue
    return sorted(found, key=lambda item: item[2], reverse=True)


def read_session(tool, ref):
    try:
        return MODULES[tool].read(ref)
    except Exception:  # an unreadable or unexpected log must not take anything down
        return None


def session_cwd(tool, ref):
    try:
        return MODULES[tool].folder(ref) or ""
    except Exception:
        return ""


def detect_tool(ref):
    """Which agent a log file or database reference belongs to."""
    text = str(ref)
    if "#" in text:
        return "cursor" if Path(text.rpartition("#")[0]).name == "state.vscdb" else "opencode"
    path = Path(text)
    if ".gemini" in path.parts:
        return "gemini"
    if ".cursor" in path.parts:
        return "cursor"
    return "codex" if ".codex" in path.parts or codex.looks_like(path) else "claude"
