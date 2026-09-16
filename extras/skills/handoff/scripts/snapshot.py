#!/usr/bin/env python3
"""Record a repo snapshot inside HANDOFF.md.

Collects what a new agent needs to check the project state -- branch, HEAD,
recent commits, uncommitted changes -- and writes it between marker comments
at the end of HANDOFF.md, replacing any previous snapshot. Creates a stub
HANDOFF.md if none exists. Prints one summary line, so the calling agent
spends almost no context on it.

Standard library only. Works on Windows, macOS and Linux.

Usage:
    python3 snapshot.py [--root DIR] [--file NAME] [--note TEXT] [--print]
"""

import argparse
import datetime
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

START = "<!-- handoff:snapshot:start -->"
END = "<!-- handoff:snapshot:end -->"
BLOCK = re.compile(r"^" + re.escape(START) + r"[ \t]*\n.*?^" + re.escape(END) + r"[ \t]*$", re.M | re.S)
MAX_STATUS_LINES = 40
MAX_RECENT_FILES = 15
MAX_WALK_FILES = 20000
SKIP_DIRS = {
    "node_modules", "venv", "env", "__pycache__", "dist", "build", "target",
    "vendor", "coverage",
}
STUB = (
    "# HANDOFF (auto-created)\n\n"
    "**Status:** Unknown - created automatically by snapshot.py; no agent has "
    "written the goal, progress, or next steps yet. Reconstruct them from the "
    "snapshot below and from the user, then fill in this file with the handoff "
    "skill template.\n"
)


def git(args, cwd):
    """Run git; return stdout without trailing whitespace, or None on any failure."""
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.rstrip()


def redact(url):
    """Drop credentials from a remote URL such as https://user:token@host/repo."""
    return re.sub(r"(?<=://)[^/@\s]+@", "", url)


def fence(text):
    return "```\n" + text + "\n```"


def git_facts(root, handoff_name="HANDOFF.md"):
    """Return (bullet lines, extra blocks, summary dict) for a git work tree."""
    lines, blocks = [], []
    sha = git(["rev-parse", "--short", "HEAD"], root)
    branch = git(["branch", "--show-current"], root) or git(["symbolic-ref", "--short", "-q", "HEAD"], root)
    if not branch:
        branch = "(detached HEAD)" if sha else "?"

    if sha:
        head = git(["log", "-1", "--format=%s (%cr)"], root) or ""
        lines.append(f"- **Branch:** `{branch}` @ `{sha}` - {head}")
    else:
        lines.append(f"- **Branch:** `{branch}` (no commits yet)")

    upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root)
    if upstream:
        counts = (git(["rev-list", "--left-right", "--count", "@{u}...HEAD"], root) or "").split()
        if len(counts) == 2:
            lines.append(f"- **Upstream:** `{upstream}` - ahead {counts[1]}, behind {counts[0]}")
        else:
            lines.append(f"- **Upstream:** `{upstream}`")
    remote = git(["remote", "get-url", "origin"], root)
    lines.append(f"- **Remote:** {redact(remote)}" if remote else "- **Remote:** none")

    status = git(["status", "--porcelain=v1", "--untracked-files=normal"], root) or ""
    # The handoff file itself is just noise in this list.
    entries = [line for line in status.splitlines() if line.strip() and line[3:] != handoff_name]
    untracked = sum(1 for line in entries if line.startswith("??"))
    changed = len(entries) - untracked
    shortstat = git(["diff", "HEAD", "--shortstat"], root) if sha else None
    detail = f" ({shortstat.strip()})" if shortstat else ""
    lines.append(f"- **Uncommitted:** {changed} changed{detail}, {untracked} untracked")

    stashes = git(["stash", "list"], root)
    if stashes:
        lines.append(f"- **Stashes:** {len(stashes.splitlines())}")

    if sha:
        log = git(["log", "-8", "--date=short", "--format=%h %ad %s"], root)
        if log:
            blocks.append("**Recent commits**\n\n" + fence(log))
    if entries:
        shown = entries[:MAX_STATUS_LINES]
        if len(entries) > MAX_STATUS_LINES:
            shown.append(f"... and {len(entries) - MAX_STATUS_LINES} more")
        blocks.append("**Working tree** (`git status --short`)\n\n" + fence("\n".join(shown)))

    summary = {"branch": branch, "sha": sha, "changed": changed, "untracked": untracked}
    return lines, blocks, summary


def recent_files(root, skip_name):
    """Most recently modified files, for projects that are not git repos."""
    found, seen = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name == skip_name:
                continue
            seen += 1
            path = Path(dirpath, name)
            try:
                found.append((path.stat().st_mtime, path))
            except OSError:
                pass
        if seen > MAX_WALK_FILES:
            break
    found.sort(reverse=True)
    rows = []
    for mtime, path in found[:MAX_RECENT_FILES]:
        when = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        rows.append(f"{when}  {path.relative_to(root).as_posix()}")
    return rows


def build_block(root, is_git, note, handoff_name):
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")
    out = [
        START,
        "## Repo snapshot (auto-generated)",
        "",
        f"_Captured {stamp} by `snapshot.py`. Compare with the live repo (`git status`) before continuing._",
    ]
    if note:
        out += ["", f"> {note}"]
    out += ["", f"- **Root:** `{root}`", f"- **OS:** {platform.system()} {platform.release()}".rstrip()]
    summary = {}
    if is_git:
        lines, blocks, summary = git_facts(root, handoff_name)
        out += lines
        for block in blocks:
            out += ["", block]
    else:
        out.append("- **Git:** not a git repository")
        rows = recent_files(root, handoff_name)
        if rows:
            out += ["", "**Recently modified files**", "", fence("\n".join(rows))]
    out.append(END)
    return "\n".join(out), summary


def read_text(path):
    """Read an existing handoff file; return (text with \\n newlines, used_crlf)."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):  # UTF-16, e.g. written by Windows PowerShell 5
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n"), "\r\n" in text


def write_block(path, block):
    text, crlf = read_text(path) if path.exists() else (STUB, False)
    match = BLOCK.search(text)  # markers count only on their own line, so notes mentioning them stay intact
    if match:
        text = text[:match.start()] + block + text[match.end():]
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    if not text.endswith("\n"):
        text += "\n"
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Record a repo snapshot inside HANDOFF.md.")
    parser.add_argument("--root", help="project directory (default: git top-level of the current directory)")
    parser.add_argument("--file", default="HANDOFF.md", help="handoff file name relative to the root (default: HANDOFF.md)")
    parser.add_argument("--note", help="extra line to show at the top of the snapshot")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print the snapshot instead of writing it")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    start = Path(args.root or os.getcwd()).resolve()
    top = git(["rev-parse", "--show-toplevel"], start)
    root = Path(top).resolve() if top else start
    block, summary = build_block(root, bool(top), args.note, args.file)

    if args.print_only:
        print(block)
        return 0

    path = root / args.file
    try:
        write_block(path, block)
    except OSError as exc:
        print(f"handoff snapshot: could not write {path}: {exc}", file=sys.stderr)
        return 1

    if top:
        detail = (f"branch {summary['branch']} @ {summary['sha'] or 'no commits'}; "
                  f"{summary['changed']} changed, {summary['untracked']} untracked")
    else:
        detail = "not a git repo"
    print(f"handoff snapshot -> {path} ({detail})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
