#!/usr/bin/env python3
"""Claude Code hook for the handoff skill: make sure HANDOFF.md exists in time.

Register this one script for PostToolUse, UserPromptSubmit and SessionStart
(`install.py --hooks` does it). It reads the hook event JSON on stdin and, when
something is worth saying, prints JSON with `additionalContext` for Claude.

It watches three things:

  Context      How full the context window is, measured from the last model
               response in the session transcript. Reminds once at
               HANDOFF_SOFT_PCT, then urgently at HANDOFF_URGENT_PCT.
  Credits      A `rate_limit` API error in the transcript means a usage or
               credit limit was hit. If HANDOFF.md is missing or older than
               that error, Claude is told to write it before anything else.
  Checkpoints  Usage limits, expired sessions and crashes arrive with no
               warning at all - nothing can predict them. So every
               HANDOFF_CHECKPOINT_MIN minutes of real work, Claude is asked to
               refresh HANDOFF.md. This is what keeps those cases survivable.

SessionStart points Claude at an unfinished HANDOFF.md, and asks it to re-read
the file right after a compaction.

Environment variables:
    HANDOFF_CONTEXT_WINDOW   context window in tokens (default 200000; it
                             switches to 1000000 by itself once usage passes it)
    HANDOFF_SOFT_PCT         first context reminder (default 60)
    HANDOFF_URGENT_PCT       urgent context reminder (default 75)
    HANDOFF_CHECKPOINT_MIN   minutes between checkpoint reminders (default 30;
                             0 turns them off)

Standard library only. On any error it exits 0 with no output, so the hook can
never get in the way of the session.
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HANDOFF_NAME = "HANDOFF.md"
CHUNK = 256 * 1024
MAX_SCAN = 16 * 1024 * 1024
RECENT_ENTRIES = 40            # how far back a rate-limit error still counts as "just now"
MIN_TOOLS_TO_REFRESH = 12      # don't nag a session that has barely done anything
MIN_TOOLS_FOR_FIRST_FILE = 25  # more work than that with no handoff at all is worth a word
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


def iso_seconds(text):
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def tail_lines(path):
    """Yield non-empty transcript lines from the end of the file, newest first."""
    with open(path, "rb") as handle:
        pos = handle.seek(0, os.SEEK_END)
        scanned, carry = 0, b""
        while pos > 0 and scanned < MAX_SCAN:
            step = min(CHUNK, pos)
            pos -= step
            scanned += step
            handle.seek(pos)
            lines = (handle.read(step) + carry).split(b"\n")
            carry = lines.pop(0)  # may be a cut-off line; the next chunk completes it
            for line in reversed(lines):
                if line.strip():
                    yield line
            if pos == 0 and carry.strip():
                yield carry


def scan_transcript(path):
    """Return (tokens in context now, timestamp of a just-happened rate-limit error)."""
    tokens, limit_at = 0, None
    for index, line in enumerate(tail_lines(path)):
        if b'"compact_boundary"' in line and parse(line).get("subtype") == "compact_boundary":
            break  # older usage belongs to the pre-compaction context
        if limit_at is None and index < RECENT_ENTRIES and b'"rate_limit"' in line:
            entry = parse(line)
            if entry.get("isApiErrorMessage") and entry.get("error") == "rate_limit":
                limit_at = entry.get("timestamp")
        if not tokens and b'"usage"' in line and b'"assistant"' in line:
            entry = parse(line)
            if entry.get("type") == "assistant" and not entry.get("isSidechain"):
                usage = (entry.get("message") or {}).get("usage") or {}
                tokens = sum(int(usage.get(key) or 0) for key in USAGE_KEYS)
        if tokens and index >= RECENT_ENTRIES:
            break
    return tokens, limit_at


def state_file(event):
    session = re.sub(r"[^A-Za-z0-9_-]", "", str(event.get("session_id") or ""))[:80] or "default"
    return STATE_DIR / f"{session}.json"


def load_state(path):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


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
        with open(path, encoding="utf-8", errors="replace") as handle:
            return bool(DONE.search(handle.read(4096)))
    except OSError:
        return False


def credit_message(handoff, limit_at, fired):
    """A usage or credit limit was just hit - the session can stop at any moment."""
    key = f"credit:{limit_at}"
    if not limit_at or key in fired:
        return None
    happened = iso_seconds(limit_at)
    if handoff.is_file() and happened and handoff.stat().st_mtime > happened:
        return None  # the handoff is already newer than the error
    fired.add(key)
    return (
        "[handoff skill] The last request hit a usage or credit limit (rate_limit). This session can "
        f"stop at any moment. Before anything else, write or refresh {handoff} with the handoff skill "
        "(goal, where we stopped, next steps), so the work can continue in another tool or after the "
        "limit resets.",
        "handoff: usage limit hit - asked Claude to write HANDOFF.md now",
    )


def context_message(tokens, fired):
    """How full the context window is."""
    if not tokens:
        return None
    window = env_int("HANDOFF_CONTEXT_WINDOW", 200_000)
    if tokens > window:  # the real window is bigger than assumed
        window = max(1_000_000, tokens)
    soft = window * env_int("HANDOFF_SOFT_PCT", 60) / 100
    urgent = window * env_int("HANDOFF_URGENT_PCT", 75) / 100
    if tokens < soft:
        for key in [key for key in fired if key.startswith(f"{window}:")]:
            fired.discard(key)  # context shrank (compaction or /clear): re-arm
        return None
    level = "urgent" if tokens >= urgent else "soft"
    if f"{window}:{level}" in fired:
        return None
    fired.update({f"{window}:{level}", f"{window}:soft"})
    pct = round(tokens * 100 / window)
    size = f"about {pct}% full (~{tokens // 1000}K of {window // 1000}K tokens)"
    if level == "soft":
        text = (f"[handoff skill] The context window is {size}. At the next natural pause, write or "
                "update HANDOFF.md at the project root with the handoff skill, so this work can be "
                "resumed in a new session or another tool if context or usage runs out.")
    else:
        text = (f"[handoff skill] The context window is {size} and automatic compaction is close. "
                "Before any other large step, write or update HANDOFF.md now with the handoff skill "
                "(goal, where we stopped, next steps), then carry on.")
    return text, f"handoff: context ~{pct}% full - asked Claude to update HANDOFF.md"


def checkpoint_message(handoff, state, now):
    """Nothing warns before a usage limit or a crash, so checkpoint on a timer."""
    minutes = env_int("HANDOFF_CHECKPOINT_MIN", 30)
    if not minutes:
        return None
    tools = int(state.get("tools") or 0)
    since = now - float(state.get("last_checkpoint") or state.get("started") or now)
    if since < minutes * 60:
        return None
    if handoff.is_file():
        if tools < MIN_TOOLS_TO_REFRESH or is_done(handoff):
            return None
        age = int((now - handoff.stat().st_mtime) / 60)
        if age < minutes:
            return None
        text = (f"[handoff skill] HANDOFF.md has not been updated in {age} minutes of work. Refresh "
                "'Where we stopped' and 'Next steps' now - a few lines is enough. Usage limits, expired "
                "sessions and crashes give no warning, so this checkpoint is what keeps the session "
                "recoverable.")
        note = f"handoff: HANDOFF.md is {age} min old - asked Claude to refresh it"
    else:
        if tools < MIN_TOOLS_FOR_FIRST_FILE:
            return None
        text = (f"[handoff skill] This session has done a lot of work and there is still no HANDOFF.md in "
                f"{handoff.parent}. Write one now with the handoff skill (goal, where we stopped, next "
                "steps) so a usage limit, an expired session or a crash cannot lose it.")
        note = "handoff: no HANDOFF.md yet - asked Claude to write one"
    state["last_checkpoint"] = now
    return text, note


def reminders(event):
    """Return (context for Claude, note for the user), or None when there is nothing to say."""
    if event.get("agent_id"):
        return None  # subagents have their own context; only the main thread writes handoffs
    handoff = project_root(event.get("cwd") or os.getcwd()) / HANDOFF_NAME
    path = state_file(event)
    state = load_state(path)
    now = time.time()
    state.setdefault("started", now)
    if event.get("hook_event_name") == "PostToolUse":
        state["tools"] = int(state.get("tools") or 0) + 1
    fired = set(state.get("fired") or [])

    tokens, limit_at = 0, None
    transcript = event.get("transcript_path")
    if transcript and os.path.isfile(transcript):
        tokens, limit_at = scan_transcript(transcript)

    message = (credit_message(handoff, limit_at, fired)
               or context_message(tokens, fired)
               or checkpoint_message(handoff, state, now))
    state["fired"] = sorted(fired)
    save_state(path, state)
    return message


def session_start(event):
    handoff = project_root(event.get("cwd") or os.getcwd()) / HANDOFF_NAME
    if event.get("source") == "compact":
        path = state_file(event)
        state = load_state(path)
        state["fired"] = []
        save_state(path, state)
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
    note = None
    if name in ("PostToolUse", "UserPromptSubmit"):
        result = reminders(event)
        if not result:
            return
        context, note = result
    elif name == "SessionStart":
        context = session_start(event)
        if not context:
            return
    else:
        return
    output = {"hookSpecificOutput": {"hookEventName": name, "additionalContext": context}}
    if note:
        output["systemMessage"] = note
    sys.stdout.write(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # never break a session over a reminder
        pass
    sys.exit(0)
