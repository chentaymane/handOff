"""OpenCode: sessions, messages and their parts in ~/.local/share/opencode/opencode.db (SQLite)."""

import os
import sqlite3
from pathlib import Path

from ..session import Session, as_dict, iso_from_ms, looks_like_limit, todo_status
from . import _db

NAME = "opencode"
LABEL = "OpenCode"
DB = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "opencode" / "opencode.db"
EDITS = {"edit": "edited", "multiedit": "edited", "patch": "edited", "write": "written"}
SHELLS = ("bash", "shell")
_cache = {}


def _sessions(database):
    """(session id, folder, last update in ms) for every top-level session; cached until the database changes."""
    stamp = _db.stamp(database)
    if stamp is None:
        return []
    if _cache.get("key") != (str(database), stamp):
        with _db.connect(database) as connection:
            rows = connection.execute(
                "select id, directory, time_updated from session where parent_id is null").fetchall()
        _cache.update(key=(str(database), stamp), sessions=rows)
    return _cache["sessions"]


def discover(max_age_hours=None):
    return [(f"{DB}#{sid}", updated / 1000) for sid, _, updated in _sessions(DB) if updated]


def folder(ref):
    database, sid = _db.split_ref(ref)
    return next((directory or "" for key, directory, _ in _sessions(database) if key == sid), "")


def read(ref):
    database, sid = _db.split_ref(ref)
    session = Session(tool=LABEL, path=str(ref), id=sid)
    with _db.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("select * from session where id = ?", (sid,)).fetchone()
        if row is None:
            return session
        messages = connection.execute(
            "select id, data from message where session_id = ? order by time_created, id", (sid,)).fetchall()
        parts = connection.execute(
            "select message_id, data from part where session_id = ? order by time_created, id", (sid,)).fetchall()
        todos = connection.execute(
            "select content, status from todo where session_id = ? order by position", (sid,)).fetchall()
    session.cwd = str(row["directory"] or "")
    session.started, session.updated = iso_from_ms(row["time_created"]), iso_from_ms(row["time_updated"])
    if "model" in row.keys():
        session.model = str(as_dict(row["model"]).get("id") or "")
    grouped = {}
    for message_id, data in parts:
        grouped.setdefault(message_id, []).append(as_dict(data))
    for message_id, data in messages:
        message = as_dict(data)
        role = message.get("role")
        said = []
        for part in grouped.get(message_id, []):
            if part.get("type") == "text" and role == "user":
                text = str(part.get("text") or "").strip()
                if text and not part.get("synthetic") and not text.startswith("<system-reminder>"):
                    said.append(text)
            else:
                _part(session, role, part)
        if said:
            session.asks.append("\n".join(said))
        if role == "assistant" and message.get("modelID"):
            session.model = str(message["modelID"])
        error = message.get("error")
        if isinstance(error, dict):
            details = error.get("data") if isinstance(error.get("data"), dict) else {}
            text = str(details.get("message") or error.get("name") or "error")
            session.error(text)
            if details.get("statusCode") == 429 or looks_like_limit(text):
                session.limit_hit = True
    if todos:
        session.plan = [(str(content), todo_status(status)) for content, status in todos]
    return session


def _part(session, role, part):
    kind = part.get("type")
    if kind == "text" and role == "assistant":
        text = str(part.get("text") or "").strip()
        if text and not part.get("synthetic"):
            session.agent_last = text
    elif kind == "tool":
        session.tool_calls += 1
        name = str(part.get("tool") or "")
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        args = state.get("input") if isinstance(state.get("input"), dict) else {}
        if name in EDITS:
            session.file(args.get("filePath") or args.get("file_path"), EDITS[name])
        elif name in SHELLS:
            session.command(args.get("command"))
        elif name == "todowrite" and isinstance(args.get("todos"), list):
            session.plan = [(str(todo.get("content") or ""), todo_status(todo.get("status")))
                            for todo in args["todos"] if isinstance(todo, dict)]
        if state.get("status") == "error":
            detail = str(state.get("error") or "failed")
            session.error(f"{name}: {detail}")
            if looks_like_limit(detail):
                session.limit_hit = True
    elif kind == "step-finish":
        tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        used = sum(int(value or 0) for value in (tokens.get("input"), tokens.get("output"),
                                                 cache.get("read"), cache.get("write")))
        if used:
            session.context_tokens = used
    elif kind == "patch":
        for file in part.get("files") or []:
            session.file(file, "edited")
    elif kind == "compaction":
        session.context_tokens = 0
