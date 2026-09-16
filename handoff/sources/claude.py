"""Claude Code (CLI, desktop app, IDE extensions): ~/.claude/projects/<project>/<session>.jsonl"""

import json
import os
from pathlib import Path

from ..session import Session, jsonl, text_of, todo_status

NAME = "claude"
LABEL = "Claude Code"
ROOT = Path.home() / ".claude" / "projects"
USAGE = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
NOISE = ("<system-reminder>", "<command-name>", "<command-message>", "<command-args>", "<local-command",
         "Caveat: The messages below")
EDITS = {"Write": "written", "Edit": "edited", "MultiEdit": "edited", "NotebookEdit": "edited"}


def discover(max_age_hours=None):
    try:
        projects = [entry.path for entry in os.scandir(ROOT) if entry.is_dir()]
    except OSError:
        return
    for project in projects:
        try:
            for item in os.scandir(project):
                if item.name.endswith(".jsonl") and item.is_file():
                    yield item.path, item.stat().st_mtime_ns / 1e9
        except OSError:
            continue


def folder(ref, max_lines=60):
    try:
        with open(ref, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle):
                if number >= max_lines:
                    break
                if '"cwd"' not in line:
                    continue
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
    for entry in jsonl(ref):
        if entry.get("isSidechain"):
            continue  # subagents: their context and chatter aren't the main session's
        session.stamp(entry.get("timestamp"))
        if isinstance(entry.get("cwd"), str) and entry["cwd"]:
            session.cwd = entry["cwd"]
        kind = entry.get("type")
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        blocks = _blocks(message)
        if kind == "system" and entry.get("subtype") == "compact_boundary":
            session.context_tokens = 0
        elif entry.get("isApiErrorMessage"):
            session.error(f"API error ({entry.get('error') or entry.get('apiErrorStatus')}): {text_of(blocks)}")
            if entry.get("error") == "rate_limit":
                session.limit_hit = True
        elif kind == "user" and not entry.get("isMeta"):
            said = []
            for block in blocks:
                if block.get("type") == "tool_result" and block.get("is_error"):
                    session.error(text_of(block.get("content")))
                elif block.get("type") == "text":
                    text = str(block.get("text") or "").strip()
                    if text and not text.startswith(NOISE):
                        said.append(text)
            if said:
                session.asks.append("\n".join(said))
        elif kind == "assistant":
            if message.get("model") and message["model"] != "<synthetic>":
                session.model = message["model"]
            usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
            tokens = sum(int(usage.get(key) or 0) for key in USAGE)
            if tokens:
                session.context_tokens = tokens
            for block in blocks:
                if block.get("type") == "text" and str(block.get("text") or "").strip():
                    session.agent_last = str(block["text"]).strip()
                elif block.get("type") == "tool_use":
                    session.tool_calls += 1
                    _tool(session, str(block.get("name") or ""), block.get("input"))
    return session


def _blocks(message):
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []


def _tool(session, name, args):
    if not isinstance(args, dict):
        return
    if name in EDITS:
        session.file(args.get("file_path") or args.get("notebook_path"), EDITS[name])
    elif name in ("Bash", "PowerShell"):
        session.command(args.get("command"))
    elif name == "TodoWrite" and isinstance(args.get("todos"), list):
        session.plan = [(str(todo.get("content") or ""), todo_status(todo.get("status")))
                        for todo in args["todos"] if isinstance(todo, dict)]
