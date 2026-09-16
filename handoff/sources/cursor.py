"""Cursor: chats from Cursor's state database, plus the agent transcripts newer versions write.

- ~/.cursor/projects/<project-slug>/agent-transcripts/<chat>/<chat>.jsonl holds messages, tool calls and
  "turn_ended" results, including errors such as "You've hit your usage limit".
- Cursor's global state.vscdb (SQLite, table cursorDiskKV): composerData:<chat> holds a chat's folder, model,
  context use and todos; bubbleId:<chat>:<bubble> holds the messages and tool calls of older chats.
"""

import os
import re
import sqlite3
import sys
from pathlib import Path

from ..session import Session, as_dict, iso_from_ms, jsonl, looks_like_limit, todo_status
from . import _db

NAME = "cursor"
LABEL = "Cursor"
TRANSCRIPTS = Path.home() / ".cursor" / "projects"
EDITS = {"edit_file_v2": "edited", "edit_file": "edited", "search_replace": "edited", "write": "written",
         "create_file": "written", "delete_file": "deleted",
         "Write": "written", "StrReplace": "edited", "Edit": "edited", "MultiEdit": "edited", "Delete": "deleted"}
SHELLS = ("run_terminal_command_v2", "run_terminal_cmd", "run_terminal_command", "Shell")
TODOS = ("todo_write", "TodoWrite")
_cache = {}


def _default_db():
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "Cursor" / "User" / "globalStorage" / "state.vscdb"


DB = _default_db()


# ---- project folders ---------------------------------------------------------------

def slug_for(folder):
    """Cursor's name for a project folder: c:/Users/me/my app -> c-Users-me-my-app."""
    return re.sub(r"[^A-Za-z0-9]+", "-", str(folder).replace(":", "")).strip("-")


def folder_from_slug(slug):
    """The existing folder a project slug stands for. Dashes are ambiguous, so the disk decides."""
    tokens = [token for token in slug.split("-") if token]
    if not tokens:
        return ""
    if os.name == "nt" and len(tokens[0]) == 1:
        return _match(tokens[0] + ":" + os.sep, tokens[1:]) or ""
    return _match(os.sep, tokens) or ""


def _match(base, tokens):
    if not tokens:
        return base
    try:
        names = {slug_for(entry.name).lower(): entry.path for entry in os.scandir(base) if entry.is_dir()}
    except OSError:
        return None
    for size in range(len(tokens), 0, -1):  # longest name first: "Memory-Skill" before "Memory"
        path = names.get("-".join(tokens[:size]).lower())
        if path:
            found = _match(path, tokens[size:])
            if found:
                return found
    return None


def _folder(data):
    identifier = data.get("workspaceIdentifier") if isinstance(data.get("workspaceIdentifier"), dict) else {}
    uri = identifier.get("uri") if isinstance(identifier.get("uri"), dict) else {}
    if uri.get("fsPath"):
        return str(uri["fsPath"])
    repos = data.get("trackedGitRepos")
    if isinstance(repos, list) and repos and isinstance(repos[0], dict):
        return str(repos[0].get("repoPath") or "")
    return ""


# ---- finding chats -----------------------------------------------------------------

def _chats(database):
    """(chat id, last update in ms, folder) for every chat in the database; cached until it changes."""
    stamp = _db.stamp(database)
    if stamp is None:
        return []
    if _cache.get("key") != (str(database), stamp):
        with _db.connect(database) as connection:
            try:
                rows = connection.execute(
                    "select key, json_extract(value, '$.lastUpdatedAt'), "
                    "json_extract(value, '$.workspaceIdentifier.uri.fsPath') "
                    "from cursorDiskKV where key like 'composerData:%'").fetchall()
            except sqlite3.OperationalError:  # no JSON support in this SQLite, or a malformed row
                rows = []
                for key, value in connection.execute("select key, value from cursorDiskKV where key like 'composerData:%'"):
                    data = as_dict(value)
                    rows.append((key, data.get("lastUpdatedAt"), _folder(data)))
        chats = [(key.split(":", 1)[1], float(updated), folder or "") for key, updated, folder in rows if updated]
        _cache.update(key=(str(database), stamp), chats=chats)
    return _cache["chats"]


def _transcripts():
    """Chat id -> (transcript path, mtime) for every agent transcript Cursor has written."""
    found = {}
    try:
        projects = [entry.path for entry in os.scandir(TRANSCRIPTS) if entry.is_dir()]
    except OSError:
        return found
    for project in projects:
        try:
            chats = [entry for entry in os.scandir(os.path.join(project, "agent-transcripts")) if entry.is_dir()]
        except OSError:
            continue
        for chat in chats:
            path = os.path.join(chat.path, chat.name + ".jsonl")
            try:
                found[chat.name] = (path, os.stat(path).st_mtime_ns / 1e9)
            except OSError:
                continue
    return found


def discover(max_age_hours=None):
    in_db = {chat: updated / 1000 for chat, updated, _ in _chats(DB)}
    on_disk = _transcripts()
    found = []
    for chat in set(in_db) | set(on_disk):
        stamp = max(in_db.get(chat, 0), on_disk.get(chat, (None, 0))[1])
        found.append((f"{DB}#{chat}" if chat in in_db else on_disk[chat][0], stamp))
    return found


def _parse_ref(ref):
    """(database or None, chat id, transcript path or None) for a reference."""
    text = str(ref)
    if "#" in text:
        database, chat = _db.split_ref(text)
        return database, chat, _transcripts().get(chat, (None, 0))[0]
    return (str(DB) if Path(DB).exists() else None), Path(text).stem, text


def folder(ref):
    database, chat, transcript = _parse_ref(ref)
    where = next((where for key, _, where in _chats(database) if key == chat), "") if database else ""
    if not where and transcript:
        where = folder_from_slug(Path(transcript).parent.parent.parent.name)
    return where


# ---- reading a chat ----------------------------------------------------------------

def read(ref):
    database, chat, transcript = _parse_ref(ref)
    session = Session(tool=LABEL, path=str(ref), id=chat)
    data, bubbles = _load(database, chat) if database else ({}, [])
    session.cwd = _folder(data)
    model = data.get("modelConfig") if isinstance(data.get("modelConfig"), dict) else {}
    session.model = str(model.get("modelName") or "")
    session.started, session.updated = iso_from_ms(data.get("createdAt")), iso_from_ms(data.get("lastUpdatedAt"))
    session.context_tokens = int(data.get("contextTokensUsed") or 0)
    session.context_window = int(data.get("contextTokenLimit") or 0)
    for bubble in bubbles:
        _bubble(session, bubble)
    guess = ""
    if transcript and os.path.exists(transcript):
        guess = _transcript(session, transcript, messages=not bubbles)
        modified = iso_from_ms(os.path.getmtime(transcript) * 1000)
        session.started = session.started or modified
        session.updated = max(session.updated, modified)
        session.cwd = session.cwd or folder_from_slug(Path(transcript).parent.parent.parent.name)
    session.cwd = session.cwd or guess
    if isinstance(data.get("todos"), list) and data["todos"]:
        session.plan = _todos(data["todos"])
    return session


def _load(database, chat):
    """A chat's composerData and its message bubbles, in conversation order."""
    with _db.connect(database) as connection:
        row = connection.execute("select value from cursorDiskKV where key = ?", (f"composerData:{chat}",)).fetchone()
        data = as_dict(row[0]) if row else {}
        keys = [f"bubbleId:{chat}:{header['bubbleId']}" for header in data.get("fullConversationHeadersOnly") or []
                if isinstance(header, dict) and header.get("bubbleId")]
        bubbles = {}
        for start in range(0, len(keys), 400):
            chunk = keys[start:start + 400]
            query = f"select key, value from cursorDiskKV where key in ({','.join('?' * len(chunk))})"
            bubbles.update((key, as_dict(value)) for key, value in connection.execute(query, chunk))
    return data, [bubbles[key] for key in keys if key in bubbles]


def _bubble(session, bubble):
    text = str(bubble.get("text") or "").strip()
    if bubble.get("type") == 1:
        if text:
            session.asks.append(text)
        return
    if text:
        session.agent_last = text
    tool = bubble.get("toolFormerData")
    if not isinstance(tool, dict) or not tool.get("name"):
        return
    name = str(tool["name"])
    _tool(session, name, as_dict(tool.get("params")) or as_dict(tool.get("rawArgs")))
    if tool.get("status") == "error":
        error = as_dict(tool.get("error"))
        detail = (error.get("clientVisibleErrorMessage") or error.get("modelVisibleErrorMessage")
                  or str(tool.get("error") or "failed"))
        session.error(f"{name}: {detail}")
        if looks_like_limit(detail):
            session.limit_hit = True


def _transcript(session, path, messages=True):
    """Apply an agent transcript; with messages=False only its errors count. Returns a guessed folder."""
    guess = ""
    for entry in jsonl(path):
        if entry.get("type") == "turn_ended":
            if entry.get("status") == "error":
                detail = str(entry.get("error") or "the turn failed")
                session.error(detail)
                if looks_like_limit(detail):
                    session.limit_hit = True
            continue
        if not messages:
            continue
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        blocks = [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []
        if entry.get("role") == "user":
            text = "\n".join(_clean(block.get("text")) for block in blocks if block.get("type") == "text").strip()
            if text:
                session.asks.append(text)
        elif entry.get("role") == "assistant":
            for block in blocks:
                if block.get("type") == "text" and _clean(block.get("text")):
                    session.agent_last = _clean(block.get("text"))
                elif block.get("type") == "tool_use":
                    found = _tool(session, str(block.get("name") or ""), block.get("input"))
                    guess = guess or found
    return guess


def _tool(session, name, args):
    """Record one tool call; returns the folder of a file it changed, as a guess at the project."""
    session.tool_calls += 1
    args = args if isinstance(args, dict) else {}
    target = args.get("relativeWorkspacePath") or args.get("path") or args.get("file_path") or args.get("targetFile")
    if name in EDITS:
        session.file(target, EDITS[name])
    elif name in SHELLS:
        session.command(args.get("command"))
    elif name in TODOS and isinstance(args.get("todos"), list):
        session.plan = _todos(args["todos"])
    if name in EDITS and isinstance(target, str) and os.path.isabs(target):
        return os.path.dirname(target)
    return ""


def _clean(text):
    return re.sub(r"</?user_query>", "", str(text or "").replace("[REDACTED]", "")).strip()


def _todos(items):
    return [(str(item.get("content") or item.get("text") or item.get("description") or ""),
             todo_status(item.get("status"))) for item in items if isinstance(item, dict)]
