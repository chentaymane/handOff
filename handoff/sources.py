"""Read coding-agent session logs from disk into one common shape.

Supported: Claude Code (~/.claude/projects) and Codex (~/.codex/sessions).
Readers are tolerant: unknown entries are skipped, and a log that cannot be
opened gives None instead of an exception, so the watcher never dies on a log
format it has not seen before.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

HOME = Path.home()
CLAUDE_PROJECTS = HOME / ".claude" / "projects"
CODEX_SESSIONS = Path(os.environ.get("CODEX_HOME") or HOME / ".codex") / "sessions"

CLAUDE_USAGE = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
CLAUDE_NOISE = ("<system-reminder>", "<command-name>", "<command-message>", "<command-args>",
                "<local-command", "Caveat: The messages below")
CLAUDE_EDITS = {"Write": "written", "Edit": "edited", "MultiEdit": "edited", "NotebookEdit": "edited"}
CODEX_SHELLS = ("shell", "shell_command", "exec_command", "local_shell")
PATCH_KINDS = {"add": "added", "delete": "deleted", "update": "edited"}
KEEP_COMMANDS = 20
KEEP_ERRORS = 10


@dataclass
class Session:
    """One agent session, reduced to what a handoff needs."""

    tool: str
    path: Path
    id: str = ""
    cwd: str = ""
    model: str = ""
    started: str = ""
    updated: str = ""
    asks: list = field(default_factory=list)       # the user's messages, oldest first
    agent_last: str = ""                           # the agent's latest reply
    plan: list = field(default_factory=list)       # the agent's own checklist: (step, status)
    plan_note: str = ""
    files: dict = field(default_factory=dict)      # path -> added / edited / written / deleted
    commands: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    tool_calls: int = 0
    context_tokens: int = 0
    context_window: int = 0                        # 0 when the log doesn't say
    limit_percent: float = None                    # share of the usage-limit window used, 0-100
    limit_window: str = ""
    limit_resets: float = None                     # epoch seconds
    limit_hit: bool = False

    def command(self, text):
        if text:
            self.commands = (self.commands + [str(text)])[-KEEP_COMMANDS:]

    def error(self, text):
        text = " ".join(str(text or "").split())
        if text:
            self.errors = (self.errors + [text])[-KEEP_ERRORS:]


def _lines(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                yield entry


def _blocks(message):
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(block.get("text") or "") for block in content if isinstance(block, dict))
    return ""


def _json(text):
    if isinstance(text, dict):
        return text
    try:
        value = json.loads(text or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _stamp(session, entry):
    stamp = entry.get("timestamp")
    if isinstance(stamp, str) and stamp:
        session.started = session.started or stamp
        session.updated = stamp


def window_label(minutes):
    """Name a usage-limit window: 300 -> '5-hour', 43200 -> '30-day'."""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return ""
    known = {300: "5-hour", 1440: "daily", 10080: "weekly", 43200: "30-day"}
    if minutes in known:
        return known[minutes]
    return f"{minutes // 60}-hour" if minutes % 60 == 0 else f"{minutes}-minute"


# ---- Claude Code -------------------------------------------------------------------

def read_claude(path):
    session = Session(tool="Claude Code", path=Path(path), id=Path(path).stem)
    for entry in _lines(path):
        if entry.get("isSidechain"):
            continue  # subagents: their context and chatter aren't the main session's
        _stamp(session, entry)
        if isinstance(entry.get("cwd"), str) and entry["cwd"]:
            session.cwd = entry["cwd"]
        kind = entry.get("type")
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        if kind == "system" and entry.get("subtype") == "compact_boundary":
            session.context_tokens = 0
        elif entry.get("isApiErrorMessage"):
            session.error(f"API error ({entry.get('error') or entry.get('apiErrorStatus')}): "
                          + _text(message.get("content")))
            if entry.get("error") == "rate_limit":
                session.limit_hit = True
        elif kind == "user" and not entry.get("isMeta"):
            said = []
            for block in _blocks(message):
                if block.get("type") == "tool_result" and block.get("is_error"):
                    session.error(_text(block.get("content")))
                elif block.get("type") == "text":
                    text = str(block.get("text") or "").strip()
                    if text and not text.startswith(CLAUDE_NOISE):
                        said.append(text)
            if said:
                session.asks.append("\n".join(said))
        elif kind == "assistant":
            if message.get("model") and message["model"] != "<synthetic>":
                session.model = message["model"]
            usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
            tokens = sum(int(usage.get(key) or 0) for key in CLAUDE_USAGE)
            if tokens:
                session.context_tokens = tokens
            for block in _blocks(message):
                if block.get("type") == "text" and str(block.get("text") or "").strip():
                    session.agent_last = str(block["text"]).strip()
                elif block.get("type") == "tool_use":
                    session.tool_calls += 1
                    _claude_tool(session, str(block.get("name") or ""), block.get("input"))
    return session


def _claude_tool(session, name, args):
    if not isinstance(args, dict):
        return
    if name in CLAUDE_EDITS:
        path = args.get("file_path") or args.get("notebook_path")
        if path:
            kind = "written" if session.files.get(path) == "written" else CLAUDE_EDITS[name]
            session.files.pop(path, None)
            session.files[path] = kind
    elif name in ("Bash", "PowerShell"):
        session.command(args.get("command"))
    elif name == "TodoWrite" and isinstance(args.get("todos"), list):
        session.plan = [(str(todo.get("content") or ""), str(todo.get("status") or ""))
                        for todo in args["todos"] if isinstance(todo, dict)]


# ---- Codex -------------------------------------------------------------------------

def read_codex(path):
    session = Session(tool="Codex", path=Path(path), id=Path(path).stem)
    applied, patched = {}, {}
    for entry in _lines(path):
        _stamp(session, entry)
        kind = entry.get("type")
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        ptype = payload.get("type")
        if kind == "session_meta":
            session.id = payload.get("id") or session.id
            session.cwd = payload.get("cwd") or session.cwd
        elif kind == "turn_context":
            session.cwd = payload.get("cwd") or session.cwd
            session.model = payload.get("model") or session.model
        elif kind == "event_msg":
            _codex_event(session, payload, ptype, applied)
        elif kind == "response_item":
            _codex_item(session, payload, ptype, patched)
    # patch_apply_end confirms what was really applied, with full paths; the patch text is a fallback
    session.files = applied or patched
    return session


def _codex_event(session, payload, ptype, applied):
    if ptype == "user_message":
        message = str(payload.get("message") or "").strip()
        marker = "## My request for Codex:"
        if marker in message:  # the IDE extension puts the open files and tabs before the request
            message = message.split(marker, 1)[1].strip()
        if message:
            session.asks.append(message)
    elif ptype == "agent_message" and payload.get("message"):
        session.agent_last = str(payload["message"]).strip()
    elif ptype == "task_complete" and payload.get("last_agent_message"):
        session.agent_last = str(payload["last_agent_message"]).strip()
    elif ptype == "task_started":
        session.context_window = int(payload.get("model_context_window") or session.context_window)
    elif ptype == "token_count":
        _codex_usage(session, payload)
    elif ptype == "patch_apply_end" and isinstance(payload.get("changes"), dict):
        for file, change in payload["changes"].items():
            kind = change.get("type") if isinstance(change, dict) else None
            applied.pop(file, None)
            applied[file] = PATCH_KINDS.get(kind, "edited")
    elif isinstance(ptype, str) and "error" in ptype:
        message = str(payload.get("message") or payload)
        session.error(message)
        if "limit" in message.lower():
            session.limit_hit = True


def _codex_item(session, payload, ptype, patched):
    if ptype == "function_call":
        session.tool_calls += 1
        name = payload.get("name")
        args = _json(payload.get("arguments"))
        if name == "update_plan" and isinstance(args.get("plan"), list):
            session.plan = [(str(item.get("step") or ""), str(item.get("status") or ""))
                            for item in args["plan"] if isinstance(item, dict)]
            session.plan_note = str(args.get("explanation") or "")
        elif name in CODEX_SHELLS:
            command = args.get("command") or args.get("cmd")
            session.command(" ".join(map(str, command)) if isinstance(command, list) else command)
    elif ptype == "custom_tool_call":
        session.tool_calls += 1
        if payload.get("name") == "apply_patch":
            text = str(payload.get("input") or "")
            for match in re.finditer(r"^\*\*\* (Add|Update|Delete) File: (.+)$", text, re.M):
                patched[match.group(2).strip()] = PATCH_KINDS[match.group(1).lower()]
    elif ptype in ("function_call_output", "custom_tool_call_output"):
        output = payload.get("output")
        output = output if isinstance(output, str) else json.dumps(output)
        code = re.match(r"\s*Exit code: (-?\d+)", output)
        if code and code.group(1) != "0":
            session.error(_failure(output))


def _failure(output):
    """The useful part of a failed command's output: what follows 'Output:'."""
    body = output.split("Output:", 1)[1] if "Output:" in output else output
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return " | ".join(lines[:3])[:300]


def _codex_usage(session, payload):
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    last = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
    tokens = int(last.get("input_tokens") or 0) + int(last.get("output_tokens") or 0)
    if tokens:
        session.context_tokens = tokens
    session.context_window = int(info.get("model_context_window") or session.context_window)
    limits = payload.get("rate_limits") if isinstance(payload.get("rate_limits"), dict) else {}
    windows = [window for window in (limits.get("primary"), limits.get("secondary"))
               if isinstance(window, dict) and window.get("used_percent") is not None]
    if windows:
        worst = max(windows, key=lambda window: float(window["used_percent"]))
        session.limit_percent = float(worst["used_percent"])
        session.limit_window = window_label(worst.get("window_minutes"))
        session.limit_resets = worst.get("resets_at")
    if limits.get("rate_limit_reached_type"):
        session.limit_hit = True


# ---- finding logs ------------------------------------------------------------------

def _subdirs(folder):
    try:
        return sorted((Path(item.path) for item in os.scandir(folder) if item.is_dir()), reverse=True)
    except OSError:
        return []


def claude_transcripts():
    """Main-session logs: ~/.claude/projects/<project>/<session>.jsonl"""
    for project in _subdirs(CLAUDE_PROJECTS):
        try:
            for item in os.scandir(project):
                if item.name.endswith(".jsonl") and item.is_file():
                    yield "claude", Path(item.path), item.stat().st_mtime
        except OSError:
            continue


def codex_transcripts(days=None):
    """~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl, newest days first."""
    oldest = date.today() - timedelta(days=days) if days else None
    for year in _subdirs(CODEX_SESSIONS):
        for month in _subdirs(year):
            for day in _subdirs(month):
                try:
                    if oldest and date(int(year.name), int(month.name), int(day.name)) < oldest:
                        return
                except ValueError:
                    pass
                try:
                    for item in os.scandir(day):
                        if item.name.endswith(".jsonl") and item.is_file():
                            yield "codex", Path(item.path), item.stat().st_mtime
                except OSError:
                    continue


def transcripts(max_age_hours=None):
    """Every known session log as (tool, path, mtime), newest first."""
    cutoff = time.time() - max_age_hours * 3600 if max_age_hours else 0
    days = int(max_age_hours // 24) + 7 if max_age_hours else None  # a long session stays in its start day's folder
    found = [item for item in list(claude_transcripts()) + list(codex_transcripts(days)) if item[2] >= cutoff]
    return sorted(found, key=lambda item: item[2], reverse=True)


def detect_tool(path):
    """Which agent wrote a log: Codex logs open with session_meta / turn_context entries."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle):
                if number >= 20:
                    break
                if '"session_meta"' in line or '"turn_context"' in line:
                    return "codex"
    except OSError:
        pass
    return "codex" if ".codex" in Path(path).parts else "claude"


READERS = {"claude": read_claude, "codex": read_codex}


def read_session(tool, path):
    try:
        return READERS[tool](path)
    except Exception:  # an unreadable or unexpected log must not take anything down
        return None


def session_cwd(tool, path, max_lines=60):
    """The working folder of a session, reading only the start of its log."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle):
                if number >= max_lines:
                    break
                if '"cwd"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                payload = entry.get("payload") if tool == "codex" else entry
                cwd = payload.get("cwd") if isinstance(payload, dict) else None
                if cwd:
                    return str(cwd)
    except OSError:
        pass
    return ""
