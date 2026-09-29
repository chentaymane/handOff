"""Freebuff and Codebuff: ~/.config/manicode/projects/<folder name>/chats/<chat id>/

Both CLIs share one data folder (FREEBUFF_CONFIG_DIR moves it). Each chat folder holds
chat-messages.json, a JSON array of {"variant": "user" | "ai" | "agent" | "error", "content",
"blocks": [{"type": "text" | "tool" | "agent", ...}], "metadata": {"usage": {...}}}, and
run-state.json, whose sessionState.fileContext names the project folder. The chat id is the
start time with ":" replaced by "-"; message timestamps are only clock times for display.
"""

import datetime
import json
import os
import re
from pathlib import Path

from ..session import Session, looks_like_limit

NAME = "codebuff"
LABEL = "Freebuff/Codebuff"
CONFIG = Path.home() / ".config"
ROOTS = ("manicode", "manicode-dev", "manicode-staging")
MESSAGES = "chat-messages.json"
RUN_STATE = "run-state.json"
USAGE = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
EDITS = {"write_file": "written", "propose_write_file": "written", "str_replace": "edited",
         "propose_str_replace": "edited"}
PATCH_KINDS = {"create_file": "added", "update_file": "edited", "delete_file": "deleted"}
ROOT_FIELD = re.compile(r'"(projectRoot|cwd)"\s*:\s*("(?:[^"\\]|\\.)*")')


def roots():
    chosen = os.environ.get("FREEBUFF_CONFIG_DIR") or os.environ.get("CODEBUFF_DATA_DIR")
    if chosen:
        return [Path(item.strip()) for item in chosen.split(",") if item.strip()]
    return [CONFIG / name for name in ROOTS]


def discover(max_age_hours=None):
    for root in roots():
        try:
            projects = [entry.path for entry in os.scandir(root / "projects") if entry.is_dir()]
        except OSError:
            continue
        for project in projects:
            try:
                chats = [entry.path for entry in os.scandir(os.path.join(project, "chats")) if entry.is_dir()]
            except OSError:
                continue
            for chat in chats:
                path = os.path.join(chat, MESSAGES)
                try:
                    yield path, os.stat(path).st_mtime_ns / 1e9
                except OSError:
                    continue


def folder(ref):
    """The project folder, from run-state.json; the data folder only keeps its name."""
    try:
        text = (Path(ref).parent / RUN_STATE).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    found = {}
    for key, value in ROOT_FIELD.findall(text):
        if key not in found:
            try:
                found[key] = json.loads(value)
            except ValueError:
                continue
    return found.get("cwd") or found.get("projectRoot") or ""


def read(ref):
    path = Path(ref)
    chat = path.parent.name
    session = Session(tool=LABEL, path=str(path), id=chat, cwd=folder(ref))
    session.started = _chat_time(chat)
    session.updated = datetime.datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
    try:
        messages = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except ValueError:
        messages = []
    for message in messages if isinstance(messages, list) else []:
        if not isinstance(message, dict):
            continue
        variant = message.get("variant")
        blocks = [block for block in message.get("blocks") or [] if isinstance(block, dict)]
        if variant == "user":
            text = str(message.get("content") or "").strip()
            if text:
                session.asks.append(text)
        elif variant in ("ai", "agent"):
            text = str(message.get("content") or "").strip() or "\n".join(
                str(block.get("content") or "") for block in blocks
                if block.get("type") == "text" and block.get("textType") != "reasoning"
                and not block.get("thinkingId")).strip()
            if text:
                session.agent_last = text
            _blocks(session, blocks)
            metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
            nested = metadata.get("codebuff") if isinstance(metadata.get("codebuff"), dict) else {}
            usage = metadata.get("usage") if isinstance(metadata.get("usage"), dict) else nested.get("usage")
            if isinstance(usage, dict):
                tokens = sum(int(usage.get(key) or 0) for key in USAGE)
                if tokens:
                    session.context_tokens = tokens
                session.model = str(usage.get("model") or metadata.get("model") or session.model)
        if variant == "error" or message.get("userError"):
            detail = str(message.get("userError") or message.get("content") or "error")
            session.error(detail)
            if looks_like_limit(detail) or "credit" in detail.lower():
                session.limit_hit = True
    return session


def _blocks(session, blocks):
    """Tool calls, including those made by the agents it spawned: Codebuff's edits are often a subagent's."""
    for block in blocks:
        if block.get("type") == "agent":
            _blocks(session, [item for item in block.get("blocks") or [] if isinstance(item, dict)])
        elif block.get("type") == "tool":
            _tool(session, str(block.get("toolName") or ""), block.get("input"), block.get("output"))


def _tool(session, name, args, output):
    session.tool_calls += 1
    args = args if isinstance(args, dict) else {}
    if name in EDITS:
        session.file(_absolute(session, args.get("path")), EDITS[name])
    elif name == "apply_patch":
        operations = args.get("operations") if isinstance(args.get("operations"), list) else [args]
        for operation in operations:
            if isinstance(operation, dict):
                session.file(_absolute(session, operation.get("path")),
                             PATCH_KINDS.get(operation.get("type"), "edited"))
    elif name == "run_terminal_command":
        session.command(args.get("command"))
    elif name == "write_todos" and isinstance(args.get("todos"), list):
        session.plan = [(str(todo.get("task") or ""), "completed" if todo.get("completed") else "pending")
                        for todo in args["todos"] if isinstance(todo, dict)]
    if isinstance(output, str) and "errorMessage" in output:
        session.error(f"{name}: {output}")


def _absolute(session, path):
    if not path:
        return ""
    return path if os.path.isabs(path) or not session.cwd else os.path.join(session.cwd, path)


def _chat_time(chat):
    """"2026-09-29T10-00-00.000Z" -> "2026-09-29T10:00:00.000Z"."""
    day, _, clock = chat.partition("T")
    return f"{day}T{clock.replace('-', ':')}" if clock else ""
