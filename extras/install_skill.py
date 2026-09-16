#!/usr/bin/env python3
"""Install the handoff skill for the coding agents on this machine.

    python install.py              copy the skill to where each agent looks for skills
    python install.py --hooks      also add the Claude Code hook that warns before the context runs out
    python install.py --rules      also add a short handoff rule to each agent's global instructions
    python install.py --uninstall  remove everything this script added
    python install.py --dry-run    show what would change, change nothing

The skill is copied, not linked, so run this again after editing the skill.
Standard library only; works on Windows, macOS and Linux.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HOME = Path.home()
SOURCE = Path(__file__).resolve().parent / "skills" / "handoff"
NAME = "handoff"
MONITOR = "context_monitor.py"
HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse")
CLAUDE_SETTINGS = HOME / ".claude" / "settings.json"

# (who reads it, skills folder, install only if this folder exists - None means always)
SKILL_TARGETS = [
    ("Claude Code", HOME / ".claude" / "skills", HOME / ".claude"),
    ("Codex, Gemini CLI, Cursor, Copilot, OpenCode and other Agent Skills tools",
     HOME / ".agents" / "skills", None),
    ("Antigravity (IDE, app and CLI)", HOME / ".gemini" / "config" / "skills", HOME / ".gemini"),
]
# (who reads it, global instructions file) - used only when the file's folder exists
RULE_TARGETS = [
    ("Claude Code", HOME / ".claude" / "CLAUDE.md"),
    ("Codex", HOME / ".codex" / "AGENTS.md"),
    ("Gemini CLI / Antigravity", HOME / ".gemini" / "GEMINI.md"),
    ("OpenCode", HOME / ".config" / "opencode" / "AGENTS.md"),
]
RULE_START, RULE_END = "<!-- handoff-skill:start -->", "<!-- handoff-skill:end -->"
RULE = "\n".join([
    RULE_START,
    "## Session handoff",
    "- At the start of a session, if the project root has a HANDOFF.md whose Status is not Done, "
    "read it before starting work and offer to continue from its \"Next steps\".",
    "- When the context window or usage budget is running low, when the user is about to switch "
    "tools, and at milestones of long tasks, write or update HANDOFF.md with the `handoff` skill.",
    RULE_END,
])
RULE_RE = re.compile(r"\n*" + re.escape(RULE_START) + r".*?" + re.escape(RULE_END) + r"\n?", re.S)


def read_file(path):
    """Return (text with \\n newlines, used CRLF); empty text if the file doesn't exist."""
    if not path.exists():
        return "", False
    text = path.read_bytes().decode("utf-8-sig")
    return text.replace("\r\n", "\n"), "\r\n" in text


def write_file(path, text, crlf, dry):
    if dry:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def is_ours(folder):
    try:
        text = (folder / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(rf"^name:\s*{NAME}\s*$", text, re.M) is not None


# ---- skill folders -----------------------------------------------------------

def install_skill(dry):
    for who, root, needs in SKILL_TARGETS:
        if needs is not None and not needs.is_dir():
            continue
        dest = root / NAME
        if dest.exists() and not is_ours(dest):
            print(f"  skip   {dest} - a different skill named '{NAME}' is already there")
            continue
        if not dry:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(SOURCE, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
        print(f"  skill  {dest}\n         read by: {who}")


def remove_skill(dry):
    for _, root, _ in SKILL_TARGETS:
        dest = root / NAME
        if dest.is_dir() and is_ours(dest):
            if not dry:
                shutil.rmtree(dest)
            print(f"  removed {dest}")


# ---- Claude Code hooks ---------------------------------------------------------

def is_monitor(hook):
    parts = [str(hook.get("command", ""))] + [str(arg) for arg in hook.get("args") or []]
    return any(MONITOR in part for part in parts)


def strip_hooks(settings):
    """Remove this skill's hook entries from a settings dict; return True if any were found."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    found = False
    for event in list(hooks):
        groups = []
        for group in hooks[event] or []:
            entries = group.get("hooks") or []
            kept = [hook for hook in entries if not is_monitor(hook)]
            if len(kept) < len(entries):
                found = True
                if kept:
                    groups.append({**group, "hooks": kept})
            else:
                groups.append(group)
        if groups:
            hooks[event] = groups
        else:
            del hooks[event]
    if found and not hooks:
        del settings["hooks"]
    return found


def load_settings():
    text, _ = read_file(CLAUDE_SETTINGS)
    return json.loads(text) if text.strip() else {}


def save_settings(settings, dry):
    backup = CLAUDE_SETTINGS.with_name("settings.json.before-handoff")
    if not dry and CLAUDE_SETTINGS.exists() and not backup.exists():
        shutil.copy2(CLAUDE_SETTINGS, backup)
    write_file(CLAUDE_SETTINGS, json.dumps(settings, indent=2) + "\n", False, dry)


def install_hooks(dry, window):
    if not (HOME / ".claude").is_dir():
        print("  skip   hooks - Claude Code is not installed (~/.claude not found)")
        return
    try:
        settings = load_settings()
    except ValueError as exc:
        print(f"  skip   hooks - {CLAUDE_SETTINGS} is not valid JSON ({exc}); add them by hand (see README)")
        return
    monitor = HOME / ".claude" / "skills" / NAME / "scripts" / MONITOR
    strip_hooks(settings)
    hooks = settings.setdefault("hooks", {})
    for event in HOOK_EVENTS:
        hooks.setdefault(event, []).append({"hooks": [
            {"type": "command", "command": sys.executable, "args": [str(monitor)], "timeout": 10}
        ]})
    if window:
        settings.setdefault("env", {})["HANDOFF_CONTEXT_WINDOW"] = str(window)
    save_settings(settings, dry)
    print(f"  hooks  {CLAUDE_SETTINGS}\n         {', '.join(HOOK_EVENTS)} -> {monitor}")
    if window:
        print(f"         context window set to {window} tokens")


def remove_hooks(dry):
    try:
        settings = load_settings()
    except ValueError:
        print(f"  skip   hooks - {CLAUDE_SETTINGS} is not valid JSON; remove the {MONITOR} entries by hand")
        return
    if strip_hooks(settings):
        env = settings.get("env") or {}
        if env.pop("HANDOFF_CONTEXT_WINDOW", None) is not None and not env:
            settings.pop("env", None)
        save_settings(settings, dry)
        print(f"  removed hooks from {CLAUDE_SETTINGS}")


# ---- global instruction rules ----------------------------------------------------

def add_rules(dry):
    for who, path in RULE_TARGETS:
        if not path.parent.is_dir():
            continue
        text, crlf = read_file(path)
        body = RULE_RE.sub("\n", text).strip("\n")
        new = (body + "\n\n" if body else "") + RULE + "\n"
        if new != text:
            write_file(path, new, crlf, dry)
        print(f"  rule   {path}  [{who}]")


def remove_rules(dry):
    for _, path in RULE_TARGETS:
        text, crlf = read_file(path)
        if RULE_START not in text:
            continue
        body = RULE_RE.sub("\n", text).strip("\n")
        if body:
            write_file(path, body + "\n", crlf, dry)
        elif not dry:
            path.unlink()
        print(f"  removed rule from {path}")


def main():
    parser = argparse.ArgumentParser(description="Install the handoff skill for your coding agents.")
    parser.add_argument("--hooks", action="store_true",
                        help="add the Claude Code hook that warns before the context runs out")
    parser.add_argument("--window", type=int, metavar="TOKENS",
                        help="with --hooks: your Claude Code context window, e.g. 1000000 (default 200000)")
    parser.add_argument("--rules", action="store_true",
                        help="add a short handoff rule to each agent's global instructions file")
    parser.add_argument("--uninstall", action="store_true", help="remove the skill, hooks and rules")
    parser.add_argument("--dry-run", action="store_true", help="show what would change without changing anything")
    args = parser.parse_args()
    if args.window and not args.hooks:
        parser.error("--window only applies together with --hooks")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if not (SOURCE / "SKILL.md").is_file():
        sys.exit(f"Can't find {SOURCE / 'SKILL.md'} - run this script from the repository.")
    if args.dry_run:
        print("Dry run - nothing is changed.\n")

    if args.uninstall:
        remove_skill(args.dry_run)
        remove_hooks(args.dry_run)
        remove_rules(args.dry_run)
        print("\nUninstalled.")
        return

    install_skill(args.dry_run)
    if args.hooks:
        install_hooks(args.dry_run, args.window)
    if args.rules:
        add_rules(args.dry_run)
    print("\nDone. Restart open agent sessions so they load the skill, then try it:\n"
          "  Claude Code / Copilot: /handoff    Codex: $handoff    any tool: \"write the handoff\"\n"
          "  To continue elsewhere: open the project and say \"Read HANDOFF.md and continue.\"")


if __name__ == "__main__":
    main()
