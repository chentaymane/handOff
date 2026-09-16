"""Gemini CLI: ~/.gemini/tmp/<project>/chats/session-*.jsonl (older versions wrote session-*.json).

<project> is a short id that ~/.gemini/projects.json maps back to the project folder.
"""

import json
import os
from pathlib import Path

from ..session import Session, jsonl, looks_like_limit, text_of, todo_status

NAME = "gemini"
LABEL = "Gemini CLI"
ROOT = Path.home() / ".gemini"
WINDOW = 1_048_576
EDITS = {"write_file": "written", "replace": "edited", "edit": "edited"}
SHELLS = ("run_shell_command", "shell")
TODOS = ("write_todos", "todo_write")


def discover(max_age_hours=None):
    try:
        projects = [entry.path for entry in os.scandir(ROOT / "tmp") if entry.is_dir()]
    except OSError:
        return
    for project in projects:
        try:
            for item in os.scandir(os.path.join(project, "chats")):
                if item.is_file() and item.name.startswith("session-") and item.name.endswith((".jsonl", ".json")):
                    yield item.path, item.stat().st_mtime_ns / 1e9
        except OSError:
            continue


def registry():
    """Project id -> project folder, read from ~/.gemini/projects.json whatever its exact layout."""
    try:
        data = json.loads((ROOT / "projects.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found = {}

    def walk(node):
        if isinstance(node, dict):
            ident, where = node.get("id") or node.get("shortId"), node.get("path") or node.get("root")
            if isinstance(ident, str) and _is_folder(where):
                found[ident] = where
            for key, value in node.items():
                if isinstance(value, str) and _is_folder(key):
                    found[value] = key
                elif isinstance(value, dict) and _is_folder(key) and isinstance(value.get("id"), str):
                    found[value["id"]] = key
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def _is_folder(text):
    return isinstance(text, str) and (text.startswith("/") or (len(text) > 2 and text[1] == ":"))


def folder(ref):
    return registry().get(Path(ref).parent.parent.name) or read(ref).cwd


def read(ref):
    path = Path(ref)
    session = Session(tool=LABEL, path=str(path), id=path.stem)
    records = [json.loads(path.read_text(encoding="utf-8"))] if path.suffix == ".json" else list(jsonl(path))
    messages = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if "$rewindTo" in record:  # the user rewound: messages from that one on are gone
            ids = [message.get("id") for message in messages]
            if record["$rewindTo"] in ids:
                del messages[ids.index(record["$rewindTo"]):]
        elif isinstance(record.get("$set"), dict):
            _header(session, record["$set"])
        elif record.get("type") and "id" in record:
            messages.append(record)
        else:
            _header(session, record)
            messages += [message for message in record.get("messages") or [] if isinstance(message, dict)]
    guess = ""
    for message in messages:
        found = _message(session, message)
        guess = guess or found
    session.cwd = registry().get(path.parent.parent.name) or session.cwd or guess
    return session


def _header(session, data):
    session.id = str(data.get("sessionId") or session.id)
    session.started = session.started or str(data.get("startTime") or "")
    if data.get("lastUpdated"):
        session.updated = str(data["lastUpdated"])
    directories = data.get("directories")
    if isinstance(directories, list) and directories and not session.cwd:
        session.cwd = str(directories[0])


def _message(session, message):
    """Apply one message; returns a folder guessed from the files it touched."""
    session.stamp(message.get("timestamp"))
    kind = message.get("type")
    text = text_of(message.get("displayContent") or message.get("content")).strip()
    guess = ""
    if kind == "user":
        if text:
            session.asks.append(text)
    elif kind == "gemini":
        if text:
            session.agent_last = text
        session.model = str(message.get("model") or session.model)
        tokens = message.get("tokens") if isinstance(message.get("tokens"), dict) else {}
        if tokens.get("input"):
            session.context_tokens = int(tokens.get("input") or 0) + int(tokens.get("output") or 0)
            session.context_window = WINDOW
        for call in message.get("toolCalls") or []:
            if isinstance(call, dict):
                found = _tool(session, call)
                guess = guess or found
    elif kind == "error":
        session.error(text)
        if looks_like_limit(text):
            session.limit_hit = True
    return guess


def _tool(session, call):
    session.tool_calls += 1
    name = str(call.get("name") or "")
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    target = args.get("file_path") or args.get("absolute_path") or args.get("path")
    if name in EDITS:
        session.file(target, EDITS[name])
    elif name in SHELLS:
        session.command(args.get("command"))
    elif name in TODOS and isinstance(args.get("todos"), list):
        session.plan = [(str(todo.get("description") or todo.get("content") or ""), todo_status(todo.get("status")))
                        for todo in args["todos"] if isinstance(todo, dict)]
    if call.get("status") == "error":
        detail = text_of(call.get("resultDisplay")) or text_of(call.get("result")) or "failed"
        session.error(f"{name}: {detail}")
        if looks_like_limit(detail):
            session.limit_hit = True
    return os.path.dirname(target) if isinstance(target, str) and os.path.isabs(target) else ""
