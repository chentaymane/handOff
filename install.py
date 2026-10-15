#!/usr/bin/env python3
"""Install the handoff skill into every coding CLI on this computer.

    python3 install.py              install or update it (Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI,
                                    OpenCode, Qwen Code, Windsurf, Goose, Amp and more: every one that is installed)
    python3 install.py --dry-run    show where it would go
    python3 install.py status       where it is installed, and which version
    python3 install.py uninstall    remove it again
    python3 install.py zip          package it as handoff-skill.zip, for uploading

On Windows, use `python` or `py -3` instead of `python3`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills", "handoff", "scripts"))

from handoff.cli import main  # noqa: E402

args = sys.argv[1:]
if not args or args[0].startswith("-"):
    args = ["install", *args]
sys.exit(main(["skill", *args]))
