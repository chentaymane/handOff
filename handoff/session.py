"""The shape every log reader produces, and the helpers the readers share."""

import datetime
import json
from dataclasses import dataclass, field

KEEP_COMMANDS = 20
KEEP_ERRORS = 10
LIMIT_WORDS = ("rate limit", "rate_limit", "ratelimit", "usage limit", "quota", "resource_exhausted",
               "credits are required", "too many requests")


@dataclass
class Session:
    """One agent session, reduced to what a handoff needs."""

    tool: str
    path: str                                      # the log file, or "<database>#<session id>"
    id: str = ""
    cwd: str = ""
    model: str = ""
    started: str = ""                              # ISO 8601
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

    def stamp(self, when):
        if isinstance(when, str) and when:
            self.started = self.started or when
            self.updated = when

    def command(self, text):
        if text:
            self.commands = (self.commands + [str(text)])[-KEEP_COMMANDS:]

    def error(self, text):
        text = " ".join(str(text or "").split())
        if text:
            self.errors = (self.errors + [text])[-KEEP_ERRORS:]

    def file(self, path, kind):
        """Record a changed file, most recent last; a file written or added stays that way when edited."""
        if not path:
            return
        path = str(path)
        previous = self.files.pop(path, None)
        if kind == "edited" and previous in ("written", "added"):
            kind = previous
        self.files[path] = kind


def jsonl(path):
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


def as_dict(value):
    """A dict from a dict, JSON text or JSON bytes; {} for anything else."""
    if isinstance(value, dict):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    try:
        value = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def text_of(content):
    """Plain text from a string, a {"text": ...} part, or a list of either."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if isinstance(content, list):
        return "\n".join(filter(None, (text_of(item) for item in content)))
    return ""


def looks_like_limit(text):
    lowered = str(text or "").lower()
    return any(word in lowered for word in LIMIT_WORDS)


def todo_status(value):
    """Map each agent's todo states onto completed / in_progress / cancelled / pending."""
    text = str(value or "").lower()
    if "complete" in text or text == "done":
        return "completed"
    if "progress" in text or text == "active":
        return "in_progress"
    if "cancel" in text:
        return "cancelled"
    return "pending"


def iso_from_ms(milliseconds):
    try:
        moment = datetime.datetime.fromtimestamp(float(milliseconds) / 1000, tz=datetime.timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return ""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


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
