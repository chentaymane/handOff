"""Qwen Code: ~/.qwen/tmp/<project>/chats/<session>.jsonl

Every record carries the working folder, so no project registry is needed. Records are Gemini API
`Content` objects: {"role", "parts": [{"text"}, {"functionCall": {"name", "args"}}, ...]}.
"""

import json
import os
from pathlib import Path

from ..session import Session, jsonl, looks_like_limit, text_of, todo_status

NAME = "qwen"
LABEL = "Qwen Code"
ROOT = Path.home() / ".qwen"
EDITS = {"write_file": "written", "edit": "edited", "replace": "edited"}
SHELLS = ("run_shell_command", "exec", "shell")
TODOS = ("todo_write", "write_todos")


def discover(max_age_hours=None):
    try:
        projects = [entry.path for entry in os.scandir(ROOT / "tmp") if entry.is_dir()]
    except OSError:
        return
    for project in projects:
        try:
            for item in os.scandir(os.path.join(project, "chats")):
                if item.is_file() and item.name.endswith(".jsonl"):
                    yield item.path, item.stat().st_mtime_ns / 1e9
        except OSError:
            continue


def folder(ref, max_lines=20):
    try:
        with open(ref, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle):
                if number >= max_lines:
                    break
                try:
                    cwd = json.loads(line).get("cwd")
                except (ValueError, AttributeError):
                    continue
                if cwd:
                    return str(cwd)
    except OSError:
        pass
    return ""


def read(ref):
    session = Session(tool=LABEL, path=str(ref), id=Path(ref).stem)
    for record in jsonl(ref):
        if record.get("isSidechain") or record.get("agentId"):
            continue  # subagents
        session.stamp(record.get("timestamp"))
        session.id = str(record.get("sessionId") or session.id)
        if isinstance(record.get("cwd"), str) and record["cwd"]:
            session.cwd = record["cwd"]
        kind, subtype = record.get("type"), record.get("subtype")
        message = record.get("message") if isinstance(record.get("message"), dict) else {}
        parts = [part for part in message.get("parts") or [] if isinstance(part, dict)]
        if kind == "user" and not subtype:
            text = "\n".join(str(part["text"]) for part in parts if part.get("text") and not part.get("thought"))
            if text.strip():
                session.asks.append(text.strip())
        elif kind == "assistant":
            session.model = str(record.get("model") or session.model)
            text = "\n".join(str(part["text"]) for part in parts if part.get("text") and not part.get("thought"))
            if text.strip():
                session.agent_last = text.strip()
            usage = record.get("usageMetadata") if isinstance(record.get("usageMetadata"), dict) else {}
            tokens = int(usage.get("totalTokenCount") or 0) or (
                int(usage.get("promptTokenCount") or 0) + int(usage.get("candidatesTokenCount") or 0))
            if tokens:
                session.context_tokens = tokens
            if record.get("contextWindowSize"):
                session.context_window = int(record["contextWindowSize"])
            for part in parts:
                call = part.get("functionCall")
                if isinstance(call, dict):
                    _tool(session, str(call.get("name") or ""), call.get("args"))
        elif kind == "tool_result":
            result = record.get("toolCallResult") if isinstance(record.get("toolCallResult"), dict) else {}
            if result.get("error") or result.get("status") == "error":
                error = result.get("error")
                detail = (error.get("message") if isinstance(error, dict) else error) or text_of(
                    result.get("resultDisplay")) or "a tool call failed"
                session.error(detail)
                if looks_like_limit(detail):
                    session.limit_hit = True
        elif kind == "system":
            payload = record.get("systemPayload") if isinstance(record.get("systemPayload"), dict) else {}
            if subtype == "chat_compression":
                session.context_tokens = int(payload.get("newTokenCount") or 0)
            elif subtype == "custom_title" and payload.get("title"):
                session.title = str(payload["title"])
            elif subtype == "notification" or payload.get("error"):
                detail = text_of(payload.get("message") or payload.get("error"))
                if detail and looks_like_limit(detail):
                    session.error(detail)
                    session.limit_hit = True
    return session


def _tool(session, name, args):
    session.tool_calls += 1
    if not isinstance(args, dict):
        return
    if name in EDITS:
        session.file(args.get("file_path") or args.get("absolute_path") or args.get("path"), EDITS[name])
    elif name in SHELLS:
        session.command(args.get("command"))
    elif name in TODOS and isinstance(args.get("todos"), list):
        session.plan = [(str(todo.get("content") or todo.get("description") or ""), todo_status(todo.get("status")))
                        for todo in args["todos"] if isinstance(todo, dict)]
