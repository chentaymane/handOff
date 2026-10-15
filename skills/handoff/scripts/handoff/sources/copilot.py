"""GitHub Copilot CLI: ~/.copilot/session-state/<session>/events.jsonl

Each line is an event, {"type", "data", "id", "parentId", "timestamp"}: session.start (with
data.context.cwd), user.message, assistant.message, tool.execution_start / _complete, session.error,
session.task_complete (with the agent's own summary), and more. Unknown events are skipped.
"""

import json
import os
import re
from pathlib import Path

from ..session import Session, jsonl, looks_like_limit, text_of, todo_status

NAME = "copilot"
LABEL = "Copilot CLI"
ROOT = Path.home() / ".copilot" / "session-state"
EDITS = {"create": "added", "edit": "edited", "str_replace": "edited", "str_replace_editor": "edited",
         "apply_patch": "edited", "write": "written", "write_file": "written"}
SHELLS = ("bash", "powershell", "shell", "run_in_terminal")
TODOS = ("update_todo", "todo_write", "write_todos")
CHECKBOX = re.compile(r"^\s*[-*]\s*\[([ xX~-])\]\s*(.+)$", re.M)


def discover(max_age_hours=None):
    try:
        folders = [entry.path for entry in os.scandir(ROOT) if entry.is_dir()]
    except OSError:
        return
    for session in folders:
        path = os.path.join(session, "events.jsonl")
        try:
            yield path, os.stat(path).st_mtime_ns / 1e9
        except OSError:
            continue


def folder(ref, max_lines=20):
    try:
        with open(ref, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle):
                if number >= max_lines:
                    break
                if '"cwd"' not in line:
                    continue
                try:
                    cwd = _cwd(json.loads(line).get("data"))
                except (ValueError, AttributeError):
                    continue
                if cwd:
                    return cwd
    except OSError:
        pass
    return _workspace(ref).get("cwd", "")


def read(ref):
    path = Path(ref)
    session = Session(tool=LABEL, path=str(path), id=path.parent.name)
    for event in jsonl(path):
        kind = str(event.get("type") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if data.get("parentToolCallId") or data.get("agentId"):
            continue  # subagents
        session.stamp(event.get("timestamp"))
        if kind == "session.start":
            session.id = str(data.get("sessionId") or session.id)
            session.cwd = _cwd(data) or session.cwd
            session.model = str(data.get("selectedModel") or data.get("model") or session.model)
        elif kind == "session.model_change":
            session.model = str(data.get("newModel") or data.get("model") or session.model)
        elif kind == "user.message":
            text = text_of(data.get("content")).strip()
            if text:
                session.asks.append(text)
                session.summary = ""  # a summary covers the work before this request
        elif kind == "assistant.message":
            text = text_of(data.get("content")).strip()
            if text:
                session.agent_last = text
        elif kind == "tool.execution_start":
            _tool(session, str(data.get("toolName") or ""), data.get("arguments"))
        elif kind == "tool.execution_complete" and data.get("success") is False:
            error = data.get("error")
            detail = (error.get("message") if isinstance(error, dict) else error) or text_of(
                (data.get("result") or {}).get("content") if isinstance(data.get("result"), dict) else "")
            _failure(session, detail or "a tool call failed")
        elif kind.endswith(".error"):
            detail = str(data.get("message") or data.get("errorType") or "error")
            _failure(session, f"{data.get('errorType')}: {detail}" if data.get("errorType") else detail)
            if data.get("statusCode") == 429 or "rate" in str(data.get("errorType") or "").lower():
                session.limit_hit = True
        elif kind == "session.task_complete" and data.get("summary"):
            session.summary = str(data["summary"])
        elif kind == "session.compaction_complete":
            session.context_tokens = 0
        if data.get("currentTokens"):
            session.context_tokens = int(data["currentTokens"])
        if data.get("tokenLimit"):
            session.context_window = int(data["tokenLimit"])
    workspace = _workspace(path)
    session.cwd = session.cwd or workspace.get("cwd", "")
    session.title = workspace.get("summary", "")
    return session


def _cwd(data):
    if not isinstance(data, dict):
        return ""
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    return str(context.get("cwd") or data.get("cwd") or "")


def _workspace(ref):
    """The flat `key: value` lines of workspace.yaml next to the events."""
    found = {}
    try:
        text = (Path(ref).parent / "workspace.yaml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return found
    for line in text.splitlines():
        key, colon, value = line.partition(":")
        value = value.strip().strip("'\"")
        if colon and key and not key.startswith((" ", "#")) and value not in ("", "|", ">", "|-", ">-"):
            found[key.strip()] = value
    return found


def _failure(session, detail):
    session.error(detail)
    if looks_like_limit(detail):
        session.limit_hit = True


def _tool(session, name, args):
    session.tool_calls += 1
    if not isinstance(args, dict):
        return
    target = args.get("path") or args.get("file_path") or args.get("filePath")
    if name in EDITS:
        session.file(target, EDITS[name])
    elif name in SHELLS:
        session.command(args.get("command"))
    elif name in TODOS:
        todos = args.get("todos")
        if isinstance(todos, list):
            session.plan = [(str(todo.get("content") or todo.get("title") or ""), todo_status(todo.get("status")))
                            for todo in todos if isinstance(todo, dict)]
        elif isinstance(todos, str):
            marks = {"x": "completed", "X": "completed", "~": "in_progress", "-": "cancelled", " ": "pending"}
            session.plan = [(step.strip(), marks[mark]) for mark, step in CHECKBOX.findall(todos)]
