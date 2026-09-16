"""Codex (CLI, IDE extension, desktop app): ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl"""

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

from ..session import Session, as_dict, jsonl, todo_status, window_label

NAME = "codex"
LABEL = "Codex"
ROOT = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
SHELLS = ("shell", "shell_command", "exec_command", "local_shell")
PATCH_KINDS = {"add": "added", "delete": "deleted", "update": "edited"}
IDE_MARKER = "## My request for Codex:"


def _subdirs(folder):
    try:
        return sorted((Path(item.path) for item in os.scandir(folder) if item.is_dir()), reverse=True)
    except OSError:
        return []


def discover(max_age_hours=None):
    # a long session stays in the folder of the day it started, so look a week further back
    oldest = date.today() - timedelta(days=int(max_age_hours // 24) + 7) if max_age_hours else None
    for year in _subdirs(ROOT):
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
                            yield item.path, item.stat().st_mtime_ns / 1e9
                except OSError:
                    continue


def looks_like(path, max_lines=20):
    """True for a Codex rollout log, which opens with session_meta / turn_context entries."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle):
                if number >= max_lines:
                    break
                if '"session_meta"' in line or '"turn_context"' in line:
                    return True
    except OSError:
        pass
    return False


def folder(ref, max_lines=60):
    try:
        with open(ref, encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle):
                if number >= max_lines:
                    break
                if '"cwd"' not in line:
                    continue
                try:
                    payload = json.loads(line).get("payload")
                except (ValueError, AttributeError):
                    continue
                if isinstance(payload, dict) and payload.get("cwd"):
                    return str(payload["cwd"])
    except OSError:
        pass
    return ""


def read(ref):
    session = Session(tool=LABEL, path=str(ref), id=Path(ref).stem)
    applied, patched = {}, Session(tool=LABEL, path=str(ref))
    for entry in jsonl(ref):
        session.stamp(entry.get("timestamp"))
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
            _event(session, payload, ptype, applied)
        elif kind == "response_item":
            _item(session, payload, ptype, patched)
    # patch_apply_end confirms what was really applied, with full paths; the patch text is only a fallback
    session.files = applied or patched.files
    return session


def _event(session, payload, ptype, applied):
    if ptype == "user_message":
        message = str(payload.get("message") or "").strip()
        if IDE_MARKER in message:  # the IDE extension puts the open files and tabs before the request
            message = message.split(IDE_MARKER, 1)[1].strip()
        if message:
            session.asks.append(message)
    elif ptype == "agent_message" and payload.get("message"):
        session.agent_last = str(payload["message"]).strip()
    elif ptype == "task_complete" and payload.get("last_agent_message"):
        session.agent_last = str(payload["last_agent_message"]).strip()
    elif ptype == "task_started":
        session.context_window = int(payload.get("model_context_window") or session.context_window)
    elif ptype == "token_count":
        _usage(session, payload)
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


def _item(session, payload, ptype, patched):
    if ptype == "function_call":
        session.tool_calls += 1
        name = payload.get("name")
        args = as_dict(payload.get("arguments"))
        if name == "update_plan" and isinstance(args.get("plan"), list):
            session.plan = [(str(item.get("step") or ""), todo_status(item.get("status")))
                            for item in args["plan"] if isinstance(item, dict)]
            session.plan_note = str(args.get("explanation") or "")
        elif name in SHELLS:
            command = args.get("command") or args.get("cmd")
            session.command(" ".join(map(str, command)) if isinstance(command, list) else command)
    elif ptype == "custom_tool_call":
        session.tool_calls += 1
        if payload.get("name") == "apply_patch":
            text = str(payload.get("input") or "")
            for match in re.finditer(r"^\*\*\* (Add|Update|Delete) File: (.+)$", text, re.M):
                patched.file(match.group(2).strip(), PATCH_KINDS[match.group(1).lower()])
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


def _usage(session, payload):
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
