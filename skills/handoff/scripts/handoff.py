#!/usr/bin/env python3
"""Run the handoff engine bundled with this skill: python3 scripts/handoff.py COMMAND (--help lists them)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the bundled `handoff` package next to this file

from handoff.cli import main  # noqa: E402

sys.exit(main())
