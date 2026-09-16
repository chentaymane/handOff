#!/usr/bin/env python3
"""Rebuild a handoff from a session that died before writing one.

When a session is cut off - usage limit, expired session, closed window, crash -
the conversation is still on disk. This prints a short digest of it (what you
asked for, what the agent did and said, the errors it hit) so an agent can read
that instead of the raw transcript, which is far too big, and write HANDOFF.md.

    python recover.py                    digest of the newest session for this folder
    python recover.py --list             list recent sessions for this folder
    python recover.py --project DIR      a different project folder
    python recover.py --file FILE.jsonl  one specific transcript
    python recover.py --events 200       keep more events (default 120)
    python recover.py --out digest.md    write to a file instead of the screen

Reads Claude Code transcripts from ~/.claude/projects. Standard library only.
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
INTERESTING = ("file_path", "command", "pattern", "path", "url", "query", "prompt", "description", "notebook_path")
SKIP_PREFIXES = ("<system-reminder>", "<command-name>", "<command-message>", "<local-command")


def short(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def slug_for(project):
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(project).resolve()))


def transcripts_for(project):
    folder = PROJECTS / slug_for(project)
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def entries(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def blocks(entry):
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def tool_summary(block):
    """One line for a tool call: its name plus the most telling argument."""
    args = block.get("input") or {}
    for key in INTERESTING:
        if args.get(key):
            return f"{block.get('name')}: {short(args[key], 110)}"
    return str(block.get("name") or "tool")


def collect(path, keep):
    """Return (header facts, first user asks, last events)."""
    facts = {"file": str(path), "session": path.stem}
    asks, events = [], []
    for entry in entries(path):
        kind = entry.get("type")
        facts.setdefault("start", entry.get("timestamp"))
        if entry.get("timestamp"):
            facts["end"] = entry["timestamp"]
        for key in ("cwd", "gitBranch", "version"):
            if entry.get(key):
                facts[key] = entry[key]
        if entry.get("isSidechain"):
            continue

        if entry.get("isApiErrorMessage"):
            texts = [b.get("text", "") for b in blocks(entry) if b.get("type") == "text"]
            events.append(f"!! API error ({entry.get('error') or entry.get('apiErrorStatus')}): "
                          f"{short(' '.join(texts), 160)}")
            if entry.get("error") == "rate_limit":
                facts["rate_limit"] = entry.get("timestamp")
            continue

        if kind == "user":
            said = []
            for block in blocks(entry):
                if block.get("type") == "tool_result" and block.get("is_error"):
                    content = block.get("content")
                    if isinstance(content, list):
                        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                    events.append(f"   !! tool error: {short(content, 160)}")
                elif block.get("type") == "text":
                    text = block.get("text", "")
                    if text.strip() and not text.lstrip().startswith(SKIP_PREFIXES):
                        said.append(text)
            if said:
                line = f"YOU: {short(' '.join(said), 400)}"
                events.append(line)
                if len(asks) < 3:
                    asks.append(short(" ".join(said), 300))
        elif kind == "assistant":
            for block in blocks(entry):
                if block.get("type") == "text" and block.get("text", "").strip():
                    events.append(f"AGENT: {short(block['text'], 400)}")
                elif block.get("type") == "tool_use":
                    events.append(f"   -> {tool_summary(block)}")

    deduped = [line for index, line in enumerate(events) if index == 0 or line != events[index - 1]]
    return facts, asks, deduped[-keep:]


def when(text):
    stamp = str(text or "")
    try:
        moment = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
        return moment.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return stamp or "?"


def digest(path, keep):
    facts, asks, events = collect(path, keep)
    out = [
        f"# Recovered session {facts['session']}",
        "",
        "This is a condensed record of a session that ended without a handoff. Use it to write "
        "HANDOFF.md at the project root (goal, where we stopped, next steps, decisions, what failed), "
        "then check it against the repo with `git status` and `git log` before continuing.",
        "",
        f"- **Transcript:** `{facts['file']}`",
        f"- **Ran:** {when(facts.get('start'))} to {when(facts.get('end'))}",
        f"- **Folder:** `{facts.get('cwd', '?')}`  **Branch:** `{facts.get('gitBranch') or '?'}`",
    ]
    if facts.get("rate_limit"):
        out.append(f"- **Ended on a usage/credit limit** at {when(facts['rate_limit'])}, so the last "
                   "steps may be unfinished.")
    if asks:
        out += ["", "## What the user asked for", ""] + [f"{n}. {ask}" for n, ask in enumerate(asks, 1)]
    out += ["", f"## Last {len(events)} events", "", "```"] + events + ["```"]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Rebuild a handoff from a dead session's transcript.")
    parser.add_argument("--project", default=os.getcwd(), help="project folder (default: current folder)")
    parser.add_argument("--file", help="a specific transcript .jsonl to read")
    parser.add_argument("--list", action="store_true", dest="list_only", help="list recent sessions and stop")
    parser.add_argument("--events", type=int, default=120, help="how many recent events to keep (default 120)")
    parser.add_argument("--out", help="write the digest to this file instead of the screen")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.file:
        path = Path(args.file)
        if not path.is_file():
            sys.exit(f"No such transcript: {path}")
    else:
        found = transcripts_for(args.project)
        if not found:
            sys.exit(f"No Claude Code sessions found for {Path(args.project).resolve()}\n"
                     f"(looked in {PROJECTS / slug_for(args.project)})")
        if args.list_only:
            for item in found[:10]:
                modified = datetime.datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                print(f"{modified}  {item.stat().st_size // 1024:>6} KB  {item.name}")
            return
        path = found[0]

    text = digest(path, args.events)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"digest written to {args.out} ({len(text.splitlines())} lines)")
    else:
        print(text)


if __name__ == "__main__":
    main()
