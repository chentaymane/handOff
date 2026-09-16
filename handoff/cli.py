"""Command line for the handoff app."""

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

from . import __version__, render, sources, system
from .watch import Watcher

EXAMPLES = """\
examples:
  handoff status          what your agents are doing and how close they are to their limits
  handoff now             write HANDOFF.md for this folder from its latest session
  handoff start           keep every project's HANDOFF.md current, in the background
  handoff autostart on    start the watcher whenever you log in
"""


def age(path):
    try:
        seconds = time.time() - path.stat().st_mtime
    except OSError:
        return "none"
    if seconds < 3600:
        return f"{int(seconds // 60)} min old"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h old"
    return f"{int(seconds // 86400)} d old"


def find_session(root, days=60):
    """The newest session, from any agent, whose working folder is `root` or inside it."""
    base = os.path.normcase(str(root)).rstrip("\\/")
    for tool, ref, _ in sources.transcripts(days * 24):
        cwd = sources.session_cwd(tool, ref)
        if not cwd:
            continue
        folder = os.path.normcase(os.path.abspath(cwd)).rstrip("\\/")
        if folder == base or folder.startswith(base + os.sep):
            return tool, ref
    return None


def cmd_status(args):
    pid = system.watcher_pid()
    print(f"Watcher:    {f'running (pid {pid})' if pid else 'not running - start it with: handoff start'}")
    print(f"Autostart:  {'on' if system.autostart_path().exists() else 'off - turn it on with: handoff autostart on'}")
    print(f"Reads:      {sources.LABELS}")
    print(f"Log file:   {system.LOG_FILE}")
    print()
    rows = []
    for tool, ref, stamp in sources.transcripts(args.days * 24)[: args.limit]:
        session = sources.read_session(tool, ref)
        if not session or not session.cwd:
            continue
        root = render.project_root(session.cwd)
        percent, window = render.context_percent(session)
        if session.limit_hit:
            usage = "LIMIT HIT"
        elif session.limit_percent is not None:
            usage = f"{session.limit_percent:.0f}% {session.limit_window}".strip()
        else:
            usage = "-"
        rows.append((
            datetime.datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M"),
            session.tool,
            f"{percent}% of {window // 1000}K" if percent is not None else "-",
            usage,
            age(root / render.HANDOFF_NAME),
            str(root),
        ))
    if not rows:
        print(f"No agent sessions in the last {args.days} days.")
        return 0
    headers = ("LAST ACTIVE", "TOOL", "CONTEXT", "USAGE LIMIT", "HANDOFF.md", "FOLDER")
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers) - 1)]
    for row in [headers, *rows]:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)) + "  " + row[-1])
    return 0


def cmd_now(args):
    if args.log:
        database = args.log.rpartition("#")[0] if "#" in args.log else args.log
        if not Path(database).is_file():
            print(f"No such session log: {args.log}")
            return 1
        tool, ref = sources.detect_tool(args.log), args.log
        folder = Path(args.folder).resolve() if args.folder else None
    else:
        folder = Path(args.folder or os.getcwd()).resolve()
        if not folder.is_dir():
            print(f"Not a folder: {folder}")
            return 1
        found = find_session(render.project_root(folder))
        if not found:
            print(f"No agent session found for {render.project_root(folder)}.")
            return 1
        tool, ref = found
    session = sources.read_session(tool, ref)
    if not session:
        print(f"Could not read {ref}.")
        return 1
    folder = folder or Path(session.cwd or os.getcwd())
    root = render.project_root(folder) if folder.is_dir() else folder
    section = render.build_section(session, root)
    if args.print:
        print(section)
        return 0
    if not root.is_dir():
        print(f"That session's folder no longer exists: {root}\nName a folder to write into: handoff now FOLDER --from LOG")
        return 1
    if root in (Path.home().resolve(), Path(root.anchor)):
        print(f"Not writing into {root} (your home folder or a drive root). Run it inside a project folder.")
        return 1
    changed = render.write_handoff(root, section)
    print(f"{'Wrote' if changed else 'Already up to date:'} {root / render.HANDOFF_NAME}"
          f"  (from {session.tool}, {Path(str(ref)).name})")
    return 0


def cmd_watch(args):
    return Watcher().run()


def cmd_start(args):
    pid, started = system.start_background()
    if not started:
        print(f"The watcher is already running (pid {pid}).")
        return 0
    time.sleep(2)
    running = system.watcher_pid()
    if not running:
        print(f"The watcher did not stay up. Try `handoff watch` to see why, or check {system.LOG_FILE}")
        return 1
    print(f"Watcher running in the background (pid {running}).")
    print("It keeps HANDOFF.md current in every project where one of your agents is working.")
    print(f"Log: {system.LOG_FILE}")
    return 0


def cmd_stop(args):
    pid = system.stop_background()
    print(f"Stopped the watcher (pid {pid})." if pid else "The watcher is not running.")
    return 0


def cmd_autostart(args):
    path = system.set_autostart(args.state == "on")
    print(f"The watcher will start when you log in ({path})." if args.state == "on" else "Autostart is off.")
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="handoff", epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Keeps HANDOFF.md current from your coding agents' session logs, so the work survives "
                    "context limits, credit limits and crashes.")
    parser.add_argument("--version", action="version", version=f"handoff {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="command")
    status = commands.add_parser("status", help="recent sessions, their context and usage limits, and the watcher")
    status.add_argument("--days", type=int, default=7, help="how far back to look (default 7)")
    status.add_argument("--limit", type=int, default=12, help="how many sessions to show (default 12)")
    now = commands.add_parser("now", help="write HANDOFF.md for a folder from its latest session")
    now.add_argument("folder", nargs="?", help="project folder (default: the current folder)")
    now.add_argument("--print", action="store_true", help="show the handoff instead of writing it")
    now.add_argument("--from", dest="log", metavar="LOG",
                     help="build it from this session log (or DATABASE#ID) instead of the folder's latest session")
    commands.add_parser("watch", help="run the watcher in this window (Ctrl+C to stop)")
    commands.add_parser("start", help="run the watcher in the background")
    commands.add_parser("stop", help="stop the background watcher")
    autostart = commands.add_parser("autostart", help="start the watcher when you log in")
    autostart.add_argument("state", choices=("on", "off"))
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handlers = {"status": cmd_status, "now": cmd_now, "watch": cmd_watch, "start": cmd_start,
                "stop": cmd_stop, "autostart": cmd_autostart}
    return handlers[args.command](args) or 0
