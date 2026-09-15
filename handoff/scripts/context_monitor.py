#!/usr/bin/env python3
"""Claude Code hook for the handoff skill: speak up before the context runs out.

Register this one script for the PostToolUse, UserPromptSubmit and SessionStart
events (`install.py --hooks` does that). It reads the hook event JSON on stdin.

PostToolUse / UserPromptSubmit
    Estimates how full the context window is from the last model response in
    the session transcript. The first time usage crosses HANDOFF_SOFT_PCT, and
    again at HANDOFF_URGENT_PCT, it asks Claude to write or update HANDOFF.md.
SessionStart
    startup/resume/clear: if the project has an unfinished HANDOFF.md, tells
    Claude it is there. compact: asks Claude to re-read (or write) HANDOFF.md,
    because details were just summarized away.

Environment variables:
    HANDOFF_CONTEXT_WINDOW  context window size in tokens (default 200000; it
                            switches to 1000000 by itself once usage passes it)
    HANDOFF_SOFT_PCT        first reminder, percent of the window (default 60)
    HANDOFF_URGENT_PCT      urgent reminder, percent of the window (default 75)

Standard library only. On any error it exits 0 with no output, so the hook
never gets in the way of the session.
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HANDOFF_NAME = "HANDOFF.md"
CHUNK = 256 * 1024
MAX_SCAN = 16 * 1024 * 1024
USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
STATE_DIR = Path(tempfile.gettempdir()) / "handoff-skill"
DONE = re.compile(r"\*\*Status:\*\*\s*Done\b", re.IGNORECASE)


def env_int(name, default):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def parse(line):
    try:
        return json.loads(line)
    except ValueError:
        return {}


def context_tokens(transcript):
    """Tokens in context at the latest main-thread model response since the last compaction.

    Reads the transcript backwards in chunks, so long sessions stay cheap.
    """
    with open(transcript, "rb") as f:
        pos = f.seek(0, os.SEEK_END)
        scanned, carry = 0, b""
        while True:
            if pos == 0 or scanned >= MAX_SCAN:
                lines, carry = ([carry] if pos == 0 else []), b""
            else:
                step = min(CHUNK, pos)
                pos -= step
                scanned += step
                f.seek(pos)
                lines = (f.read(step) + carry).split(b"\n")
                carry = lines.pop(0)  # may be cut off; completed by the next chunk
            if not lines:
                return 0
            for line in reversed(lines):
                if b'"compact_boundary"' in line and parse(line).get("subtype") == "compact_boundary":
                    return 0  # older usage belongs to the pre-compaction context
                if b'"usage"' not in line or b'"assistant"' not in line:
                    continue
                entry = parse(line)
                if entry.get("type") != "assistant" or entry.get("isSidechain"):
                    continue
                usage = (entry.get("message") or {}).get("usage") or {}
                tokens = sum(int(usage.get(key) or 0) for key in USAGE_KEYS)
                if tokens:
                    return tokens


def state_file(event):
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(event.get("session_id") or ""))[:80] or "default"
    return STATE_DIR / f"{session}.json"


def load_fired(path):
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("fired", []))
    except (OSError, ValueError, AttributeError):
        return set()


def save_fired(path, fired):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fired": sorted(fired)}), encoding="utf-8")
    except OSError:
        pass


def check_context(event):
    """Return (context for Claude, message for the user) when a threshold is newly crossed."""
    transcript = event.get("transcript_path")
    if event.get("agent_id") or not transcript or not os.path.isfile(transcript):
        return None  # subagents have their own context; only the main thread writes handoffs
    used = context_tokens(transcript)
    if not used:
        return None
    window = env_int("HANDOFF_CONTEXT_WINDOW", 200_000)
    if used > window:  # the real window is bigger than assumed
        window = max(1_000_000, used)
    soft = window * env_int("HANDOFF_SOFT_PCT", 60) / 100
    urgent = window * env_int("HANDOFF_URGENT_PCT", 75) / 100

    path = state_file(event)
    fired = load_fired(path)
    if used < soft:
        if fired:  # context shrank (compaction or /clear): re-arm the reminders
            save_fired(path, set())
        return None
    level = "urgent" if used >= urgent else "soft"
    if f"{window}:{level}" in fired:
        return None
    fired.update({f"{window}:{level}", f"{window}:soft"})
    save_fired(path, fired)

    pct = round(used * 100 / window)
    size = f"about {pct}% full (~{used // 1000}K of {window // 1000}K tokens)"
    if level == "soft":
        context = (f"[handoff skill] The context window is {size}. At the next natural pause, "
                   "write or update HANDOFF.md at the project root with the handoff skill, so this "
                   "work can be resumed in a new session or another tool if context or usage runs out.")
    else:
        context = (f"[handoff skill] The context window is {size} and automatic compaction is close. "
                   "Before any other large step, write or update HANDOFF.md now with the handoff skill "
                   "(goal, where we stopped, next steps), then carry on.")
    return context, f"handoff: context ~{pct}% full - asked Claude to update HANDOFF.md"


def project_root(cwd):
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(cwd)


def is_done(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return bool(DONE.search(f.read(4096)))
    except OSError:
        return False


def session_start(event):
    handoff = project_root(event.get("cwd") or os.getcwd()) / HANDOFF_NAME
    if event.get("source") == "compact":
        save_fired(state_file(event), set())
        if handoff.is_file():
            return (f"[handoff skill] The conversation was just compacted, so details may be missing. "
                    f"Re-read {handoff} before continuing, and keep it updated.")
        return ("[handoff skill] The conversation was just compacted. If you are in the middle of a "
                "multi-step task, write HANDOFF.md now with the handoff skill while the details are "
                "still in the summary.")
    if not handoff.is_file() or is_done(handoff):
        return None
    modified = datetime.datetime.fromtimestamp(handoff.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return (f"[handoff skill] This project has an unfinished HANDOFF.md from an earlier session "
            f"(last modified {modified}): {handoff}. If the user wants to continue that work or asks "
            "what is next, read it first and resume from its Next steps.")


def main():
    event = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    name = event.get("hook_event_name")
    user_message = None
    if name in ("PostToolUse", "UserPromptSubmit"):
        result = check_context(event)
        if not result:
            return
        context, user_message = result
    elif name == "SessionStart":
        context = session_start(event)
        if not context:
            return
    else:
        return
    output = {"hookSpecificOutput": {"hookEventName": name, "additionalContext": context}}
    if user_message:
        output["systemMessage"] = user_message
    sys.stdout.write(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # never break the session over a reminder
        pass
    sys.exit(0)
