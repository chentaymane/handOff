"""Turn a Session into the auto-maintained part of HANDOFF.md, and write it safely."""

import datetime
import os
import re
import subprocess
from pathlib import Path

HANDOFF_NAME = "HANDOFF.md"
START = "<!-- handoff:auto:start -->"
END = "<!-- handoff:auto:end -->"
STAMP = re.compile(r"^_Last update: .*$", re.M)
APP_URL = "https://github.com/chentaymane/handoff"
AGENT_DIRS = (".claude", ".codex", ".gemini", ".cursor", ".copilot", ".handoff")  # agents' own files, not projects
MAX_FILES = 25
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # keep git from flashing console windows

SECRETS = [
    (re.compile(r"(?<=://)[^/@\s]+@"), ""),                                               # user:password@ in URLs
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[redacted]"),                               # OpenAI, Anthropic
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "[redacted]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[redacted]"),                                  # AWS
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), "[redacted]"),                       # Slack
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}"), "[redacted]"),                               # Google
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "[redacted]"),  # JWT
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)(\s*[:=]\s*)(['\"]?)[^\s'\"]{6,}"),
     r"\1\2\3[redacted]"),
]


def redact(text):
    text = str(text or "")
    for pattern, replacement in SECRETS:
        text = pattern.sub(replacement, text)
    return text


def one_line(text, limit):
    text = " ".join(redact(text).split()).replace("`", "'")
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def quote(text, limit):
    """Text as a Markdown blockquote, redacted, trimmed, without runs of blank lines."""
    text = redact(text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + " ..."
    out, blank = [], False
    for line in text.splitlines():
        if line.strip():
            out.append("> " + line.rstrip())
            blank = False
        elif not blank:
            out.append(">")
            blank = True
    return "\n".join(out) or "> (empty)"


def local_time(stamp):
    try:
        moment = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return str(stamp or "?")
    return moment.astimezone().strftime("%Y-%m-%d %H:%M")


def epoch_time(seconds):
    try:
        return datetime.datetime.fromtimestamp(float(seconds)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return "?"


def context_percent(session):
    """(percent, window) of the context in use; the window is guessed when the log doesn't say."""
    if not session.context_tokens:
        return None, 0
    window = session.context_window or (200_000 if session.context_tokens <= 200_000 else 1_000_000)
    return round(session.context_tokens * 100 / window), window


def relative(path, root):
    path = str(path)
    if not os.path.isabs(path):
        return path.replace("\\", "/")
    base = str(root).rstrip("\\/")
    if os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(base) + os.sep):
        return os.path.abspath(path)[len(base) + 1:].replace("\\", "/")
    return path


def agent_file(path):
    """True for files agents keep for themselves (memory, settings) rather than project files."""
    path = str(path)
    if not os.path.isabs(path):
        return False
    full = os.path.normcase(os.path.abspath(path))
    home = os.path.normcase(str(Path.home()))
    return any(full.startswith(os.path.join(home, name) + os.sep) for name in AGENT_DIRS)


# ---- git ---------------------------------------------------------------------------

def git(args, cwd):
    try:
        result = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=20,
                                creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return result.stdout.rstrip() if result.returncode == 0 else None


def project_root(folder):
    """The git top level of a folder, or the folder itself outside git."""
    top = git(["rev-parse", "--show-toplevel"], folder)
    return Path(top).resolve() if top else Path(folder).resolve()


def repo_lines(root):
    sha = git(["rev-parse", "--short", "HEAD"], root)
    if sha is None and git(["rev-parse", "--is-inside-work-tree"], root) is None:
        return ["- Not a git repository."]
    branch = git(["branch", "--show-current"], root) or ("(detached)" if sha else "?")
    if sha:
        subject = git(["log", "-1", "--format=%s"], root) or ""
        lines = [f"- **Branch:** `{branch}` @ `{sha}` - {one_line(subject, 120)}"]
    else:
        lines = [f"- **Branch:** `{branch}` (no commits yet)"]
    upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], root)
    if upstream:
        counts = (git(["rev-list", "--left-right", "--count", "@{u}...HEAD"], root) or "").split()
        if len(counts) == 2:
            lines.append(f"- **Upstream:** `{upstream}` - ahead {counts[1]}, behind {counts[0]}")
    status = git(["status", "--porcelain=v1", "--untracked-files=normal"], root) or ""
    entries = [line for line in status.splitlines() if line.strip() and line[3:] != HANDOFF_NAME]
    untracked = sum(1 for line in entries if line.startswith("??"))
    lines.append(f"- **Uncommitted:** {len(entries) - untracked} changed, {untracked} untracked")
    if sha:
        log = git(["log", "-5", "--date=short", "--format=%h %ad %s"], root)
        if log:
            lines += ["", "Recent commits:", "", "```", redact(log), "```"]
    if entries:
        shown = entries[:20] + ([f"... and {len(entries) - 20} more"] if len(entries) > 20 else [])
        lines += ["", "Working tree:", "", "```", *shown, "```"]
    return lines


# ---- the section -------------------------------------------------------------------

def heads_up(session):
    notes = []
    if session.limit_hit:
        notes.append("this session hit its usage limit, so its last step may be unfinished")
    elif session.limit_percent is not None and session.limit_percent >= 80:
        notes.append(f"{session.limit_percent:.0f}% of the usage limit is used")
    percent, _ = context_percent(session)
    if percent is not None and percent >= 70:
        notes.append(f"the context window is {percent}% full")
    return "; ".join(notes)


def build_section(session, root):
    now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")
    model = f" ({session.model})" if session.model else ""
    out = [
        START,
        "## Auto handoff",
        "",
        f"_Last update: {now}, from a **{session.tool}** session{model}. Kept current by the "
        f"[handoff app]({APP_URL}): this section is rewritten automatically, anything outside it is kept._",
    ]
    warning = heads_up(session)
    if warning:
        out += ["", f"**Heads-up:** {warning}."]

    out += ["", "### Goal"]
    if session.asks:
        out.append(quote(session.asks[0], 900))
        if len(session.asks) > 1 and session.asks[-1].strip() != session.asks[0].strip():
            out += ["", "**Latest request:**", "", quote(session.asks[-1], 600)]
    else:
        out.append("_No request from the user found in the log._")

    out += ["", "### Where we stopped"]
    out.append(quote(session.agent_last, 1500) if session.agent_last else "_The agent had not replied yet._")

    if session.plan:
        out += ["", "### Plan"]
        for step, status in session.plan:
            label = one_line(step, 200)
            if status == "in_progress":
                label = f"**{label}** _(in progress)_"
            out.append(f"- [{'x' if status == 'completed' else ' '}] {label}")
        if session.plan_note:
            out += ["", quote(session.plan_note, 500)]

    out += ["", "### Next steps"]
    remaining = [step for step, status in session.plan if status != "completed"]
    if remaining:
        out += [f"{number}. {one_line(step, 200)}" for number, step in enumerate(remaining, 1)]
    else:
        out += ["1. Read \"Where we stopped\" and finish anything it left open.",
                "2. Run `git status` to find uncommitted or half-finished edits before starting new work."]

    files = [(path, kind) for path, kind in session.files.items() if not agent_file(path)]
    if files:
        out += ["", "### Files changed in this session"]
        if len(files) > MAX_FILES:
            out.append(f"_The last {MAX_FILES} of {len(files)} files:_")
        out += [f"- `{one_line(relative(path, root), 160)}` - {kind}" for path, kind in files[-MAX_FILES:]]
    if session.commands:
        out += ["", "### Recent commands"]
        out += [f"- `{one_line(command, 160)}`" for command in session.commands[-8:]]
    if session.errors:
        out += ["", "### Errors seen"]
        out += [f"- {one_line(error, 240)}" for error in session.errors[-5:]]

    out += ["", "### Session",
            f"- **Tool:** {session.tool}{model}, {session.tool_calls} tool calls",
            f"- **Active:** {local_time(session.started)} to {local_time(session.updated)}"]
    percent, window = context_percent(session)
    if percent is not None:
        guessed = "" if session.context_window else ", window size assumed"
        out.append(f"- **Context:** ~{session.context_tokens // 1000}K of {window // 1000}K tokens "
                   f"({percent}%{guessed})")
    if session.limit_percent is not None or session.limit_hit:
        usage = f"{session.limit_percent:.0f}% used" if session.limit_percent is not None else ""
        if session.limit_window:
            usage += f" of the {session.limit_window} window"
        if session.limit_resets:
            usage += f", resets {epoch_time(session.limit_resets)}"
        if session.limit_hit:
            usage = (usage + " - " if usage else "") + "**limit reached**"
        out.append(f"- **Usage limit:** {usage}")
    out.append(f"- **Full log:** `{session.path}`")

    out += ["", "### Repo", *repo_lines(root), END]
    return "\n".join(out)


# ---- writing -----------------------------------------------------------------------

def header(root):
    return (f"# HANDOFF: {Path(root).name}\n\n"
            "> **Next agent:** read this file, check it against the repo with `git status`, then continue "
            "from \"Next steps\". The section below is updated automatically from the latest coding session "
            "in this folder; notes added outside it are kept.\n")


def read_text(path):
    """(text with \\n newlines, whether the file used CRLF)."""
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    return text.replace("\r\n", "\n"), "\r\n" in text


def write_handoff(root, section):
    """Insert or replace the auto section of HANDOFF.md. Returns True if the file changed."""
    path = Path(root) / HANDOFF_NAME
    exists = path.exists()
    text, crlf = read_text(path) if exists else (header(root), False)
    start, end = text.find(START), text.find(END)
    if start != -1 and end > start:
        new = text[:start] + section + text[end + len(END):]
    else:
        new = text.rstrip("\n") + "\n\n" + section + "\n"
    if not new.endswith("\n"):
        new += "\n"
    if exists and STAMP.sub("", new) == STAMP.sub("", text):
        return False  # only the timestamp would change
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes((new.replace("\n", "\r\n") if crlf else new).encode("utf-8"))
    os.replace(temporary, path)
    return True
