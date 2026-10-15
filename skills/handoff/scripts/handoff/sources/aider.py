"""Aider: .aider.chat.history.md, kept in the project folder itself.

Aider has no central log folder, so project folders are found by looking one and two levels
inside the usual places for code (set HANDOFF_SCAN to a list of folders to look in instead).
The file is Markdown: each run starts with "# aider chat started at ...", the user's messages
are "#### " lines, Aider's own output is "> " lines, and the model's replies are plain text.
"""

import datetime
import os
import re
import time
from pathlib import Path

from ..session import Session, looks_like_limit

NAME = "aider"
LABEL = "Aider"
HISTORY = ".aider.chat.history.md"
PLACES = ("", "Desktop", "Documents", "projects", "Projects", "code", "Code", "src", "dev", "work", "repos",
          "git", "github", "GitHub", "workspace", "Developer")
RESCAN_SECONDS = 60
SKIP = {"node_modules", "venv", ".venv", "Library", "AppData", "snap", "go", "Pictures", "Music", "Videos"}
RUN = re.compile(r"^# aider chat started at (.+)$", re.M)
TOKENS = re.compile(r"Tokens: ([\d.]+)([kM]?) sent, ([\d.]+)([kM]?) received")
TOO_BIG = re.compile(r"estimated chat context of ([\d,]+) tokens exceeds the ([\d,]+) token limit")
MODEL = re.compile(r"^(?:Main model|Model): (\S+)")
_found = {"at": 0.0, "paths": []}


def places():
    chosen = os.environ.get("HANDOFF_SCAN")
    if chosen:
        return [Path(item).expanduser() for item in chosen.split(os.pathsep) if item]
    return [Path.home() / name for name in PLACES]


def _scan():
    """Every Aider history file one or two levels inside the places, cached for a minute."""
    if time.time() - _found["at"] < RESCAN_SECONDS:
        return _found["paths"]
    paths, seen = [], set()

    def look(folder, depth):
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        for entry in entries:
            if entry.name == HISTORY and depth > 0 and entry.is_file() and entry.path not in seen:
                seen.add(entry.path)
                paths.append(entry.path)
            elif depth < 2 and entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".") \
                    and entry.name not in SKIP:
                look(entry.path, depth + 1)

    for place in places():
        look(place, 0)
    _found.update(at=time.time(), paths=paths)
    return paths


def discover(max_age_hours=None):
    for path in _scan():
        try:
            yield path, os.stat(path).st_mtime_ns / 1e9
        except OSError:
            continue


def folder(ref):
    return str(Path(ref).parent)


def read(ref):
    path = Path(ref)
    session = Session(tool=LABEL, path=str(path), id=path.parent.name, cwd=str(path.parent))
    text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    starts = [match for match in RUN.finditer(text)]
    runs = [(match.group(1), text[match.end():starts[i + 1].start() if i + 1 < len(starts) else len(text)])
            for i, match in enumerate(starts)] or [("", text)]
    # The latest run in which the user asked for something: a run that only started aider says nothing.
    started, body = next((run for run in reversed(runs) if "\n#### " in "\n" + run[1]), runs[-1])
    session.started = _iso(started)
    session.updated = datetime.datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
    session.id = f"{path.parent.name} {started}".strip()

    reply, asking = [], []

    def flush_ask():
        if asking:
            said = "\n".join(asking).strip()
            command, _, rest = said.partition(" ")
            if said.startswith("/"):
                if command in ("/run", "/test"):
                    session.command(rest)
                elif command in ("/ask", "/code", "/architect") and rest.strip():
                    session.asks.append(rest.strip())
            elif said:
                session.asks.append(said)
            asking.clear()

    def flush_reply():
        said = "\n".join(reply).strip()
        if said:
            session.agent_last = said
        reply.clear()

    for line in body.split("\n"):
        if line.startswith("#### ") or line == "####":
            if not asking:
                flush_reply()
            asking.append(line[5:])
            continue
        flush_ask()
        if line.startswith(">"):
            _note(session, line[1:].strip())
        else:
            reply.append(line)
    flush_ask()
    flush_reply()
    return session


def _note(session, line):
    """One line of Aider's own output."""
    tokens = TOKENS.search(line)
    model = MODEL.match(line)
    too_big = TOO_BIG.search(line)
    if tokens:
        sent, received = _count(tokens.group(1), tokens.group(2)), _count(tokens.group(3), tokens.group(4))
        session.context_tokens = sent + received
    elif model:
        session.model = model.group(1)
    elif too_big:
        session.context_tokens = int(too_big.group(1).replace(",", ""))
        session.context_window = int(too_big.group(2).replace(",", ""))
        session.error(line)
    elif line.startswith("Applied edit to "):
        session.tool_calls += 1
        session.file(os.path.join(session.cwd, line[len("Applied edit to "):].strip()), "edited")
    elif line.startswith("Running "):
        session.tool_calls += 1
        session.command(line[len("Running "):])
    elif "Error" in line or "error:" in line.lower() or looks_like_limit(line):
        session.error(line)
        if looks_like_limit(line):
            session.limit_hit = True


def _count(number, unit):
    return int(float(number) * {"k": 1_000, "M": 1_000_000}.get(unit, 1))


def _iso(stamp):
    try:
        return datetime.datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S").astimezone().isoformat()
    except ValueError:
        return ""
