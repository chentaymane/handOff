"""Command line for the handoff app."""

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

from . import __version__, app, render, sources, system
from .watch import Watcher

EXAMPLES = """\
examples:
  handoff install         one step: add the `handoff` command, start the watcher, start it at every login
  handoff dashboard       open the local web dashboard (http://127.0.0.1:7788)
  handoff status          what your agents are doing and how close they are to their limits
  handoff now             write HANDOFF.md for this folder from its latest session
  handoff start           keep every project's HANDOFF.md current, in the background
  handoff autostart on    start the watcher whenever you log in
"""


def cmd_status(args):
    state = app.watcher_state()
    pid = state["pid"]
    print(f"Watcher:    {f'running (pid {pid})' if pid else 'not running - start it with: handoff start'}")
    print(f"Autostart:  {'on' if state['autostart'] else 'off - turn it on with: handoff autostart on'}")
    print(f"Reads:      {sources.LABELS}")
    print(f"Log file:   {state['log']}")
    print()
    rows = []
    for row in app.overview(args.days, args.limit):
        if row["limit_hit"]:
            usage = "LIMIT HIT"
        elif row["limit_percent"] is not None:
            usage = f"{row['limit_percent']:.0f}% {row['limit_window']}".strip()
        else:
            usage = "-"
        percent = row["context_percent"]
        rows.append((
            datetime.datetime.fromtimestamp(row["active"]).strftime("%Y-%m-%d %H:%M"),
            row["tool"],
            f"{percent}% of {row['context_window'] // 1000}K" if percent is not None else "-",
            usage,
            app.age_text(row["handoff_age"]),
            row["folder"],
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
        found = app.find_session(render.project_root(folder))
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
    return Watcher(echo=lambda message: print(message, flush=True)).run()


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


def cmd_dashboard(args):
    from . import dashboard

    return dashboard.serve(args.port, open_browser=not args.no_open)


def cmd_install(args):
    path, on_path, note = system.install_launcher()
    if note == "installed":
        print(f"Command:    {path}")
        if not on_path:
            print(f"            {path.parent} is not on your PATH yet. Add this line to ~/.bashrc or ~/.zshrc:")
            print(f'            export PATH="{path.parent}:$PATH"')
    else:
        print(f"Command:    {path} ({note})")
    print(f"Autostart:  on ({system.set_autostart(True)})")
    code = cmd_start(args)
    print()
    print("From now on, every project you work on with a coding agent keeps a HANDOFF.md up to date.")
    print("When a session hits a limit, open the project in any other agent and say:")
    print('    "Read HANDOFF.md and continue."')
    print("For a session that already ended, run `handoff now` inside its project folder.")
    return code


def cmd_uninstall(args):
    cmd_stop(args)
    system.set_autostart(False)
    print("Autostart is off.")
    removed = system.remove_launcher()
    if removed:
        print(f"Removed {removed}")
    print(f"HANDOFF.md files in your projects are kept. The app's own files are in {system.APP_DIR}.")
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
    board = commands.add_parser("dashboard", help="open the local web dashboard (this computer only)")
    board.add_argument("--port", type=int, default=7788, help="port to use (default 7788, or the next free one)")
    board.add_argument("--no-open", action="store_true", help="don't open a browser window")
    commands.add_parser("install", help="add the `handoff` command, start the watcher and start it at login")
    commands.add_parser("uninstall", help="stop the watcher, turn autostart off and remove the `handoff` command")
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
                "stop": cmd_stop, "autostart": cmd_autostart, "install": cmd_install, "uninstall": cmd_uninstall,
                "dashboard": cmd_dashboard}
    return handlers[args.command](args) or 0
