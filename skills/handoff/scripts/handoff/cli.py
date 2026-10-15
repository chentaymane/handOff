"""Command line for handoff: the skill's scripts, and the optional background app."""

import argparse
import datetime
import itertools
import os
import sys
import time
from pathlib import Path

from . import __version__, app, render, skill, sources, system
from .watch import Watcher

PYTHON = "python" if os.name == "nt" else "python3"  # what people type to run Python on this system

EXAMPLES = """\
examples:
  handoff skill install      copy this skill into every coding CLI on this computer
  handoff now                write HANDOFF.md for this folder from its latest session
  handoff now --tool codex   ... from this folder's latest Codex session
  handoff sessions           this folder's sessions from every CLI, to recover one that ended
  handoff status             what your agents are doing and how close they are to their limits
  handoff install            optional: a background watcher that keeps every HANDOFF.md current
  handoff dashboard          open the local web dashboard (http://127.0.0.1:7788)
"""


def prog():
    """How this copy was started, for the commands it suggests: `handoff`, the skill's script, or install.py."""
    script = Path(sys.argv[0])
    if script.name in ("handoff.py", "install.py"):
        return f"{PYTHON} {script}"
    return "handoff"


def tool_arg(text):
    name = sources.tool_name(text)
    if not name:
        raise argparse.ArgumentTypeError(f"unknown agent {text!r}; choose from {', '.join(sources.MODULES)}, "
                                         "or use --repo-only for other agents")
    return name


def cmd_status(args):
    state = app.watcher_state()
    pid = state["pid"]
    print(f"Watcher:    {f'running (pid {pid})' if pid else f'not running - start it with: {prog()} start'}")
    print(f"Autostart:  {'on' if state['autostart'] else f'off - turn it on with: {prog()} autostart on'}")
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
        root = render.project_root(folder)
        found = None if args.repo_only else app.find_session(root, tool=args.tool)
        if not found:
            if not args.repo_only and not args.tool:
                print(f"No agent session found for {root}.\nTo write the repo facts only: {prog()} now --repo-only")
                return 1
            reason = ("no session log was read" if args.repo_only
                      else f"no {sources.MODULES[args.tool].LABEL} session found for this folder")
            return write_section(root, render.build_repo_section(root, reason), args.print, "repo facts only")
        tool, ref = found
    session = sources.read_session(tool, ref)
    if not session:
        print(f"Could not read {ref}.")
        return 1
    folder = folder or Path(session.cwd or os.getcwd())
    root = render.project_root(folder) if folder.is_dir() else folder
    return write_section(root, render.build_section(session, root), args.print,
                         f"from {session.tool}, {Path(str(ref)).name}")


def write_section(root, section, print_only, source):
    if print_only:
        print(section)
        return 0
    if not root.is_dir():
        print(f"That session's folder no longer exists: {root}\n"
              f"Name a folder to write into: {prog()} now FOLDER --from LOG")
        return 1
    if root in (Path.home().resolve(), Path(root.anchor)):
        print(f"Not writing into {root} (your home folder or a drive root). Run it inside a project folder.")
        return 1
    changed = render.write_handoff(root, section)
    print(f"{'Wrote' if changed else 'Already up to date:'} {root / render.HANDOFF_NAME}  ({source})")
    return 0


def cmd_sessions(args):
    root = render.project_root(Path(args.folder or os.getcwd()).resolve())
    found = list(itertools.islice(app.folder_sessions(root, args.days, args.tool), args.limit))
    if not found:
        print(f"No agent sessions for {root} in the last {args.days} days.")
        return 0
    print(f"Sessions in {root}, newest first:")
    for number, (tool, ref, stamp) in enumerate(found, 1):
        session = sources.read_session(tool, ref)
        if not session:
            print(f"\n{number}. {sources.MODULES[tool].LABEL} - log could not be read\n   Log: {ref}")
            continue
        facts = [f"last active {render.epoch_time(stamp)}"]
        if session.limit_hit:
            facts.append("USAGE LIMIT HIT")
        elif session.limit_percent is not None:
            facts.append(f"{session.limit_percent:.0f}% of the usage limit used")
        percent, window = render.context_percent(session)
        if percent is not None:
            facts.append(f"context {percent}% of {window // 1000}K")
        model = f" ({session.model})" if session.model else ""
        print(f"\n{number}. {session.tool}{model} - {', '.join(facts)}")
        if session.asks:
            print(f"   First request:  {render.one_line(session.asks[0], 160)}")
        if len(session.asks) > 1:
            print(f"   Latest request: {render.one_line(session.asks[-1], 160)}")
        if session.agent_last:
            print(f"   Last reply:     {render.one_line(session.agent_last, 200)}")
        print(f"   Log: {ref}")
    print(f'\nRead one:               {prog()} now --from "LOG" --print')
    print(f'Write it to HANDOFF.md: {prog()} now --from "LOG"')
    return 0


def show(results):
    """One line per CLI; the ones that aren't on this computer go on a single line at the end."""
    absent = [target["key"] for target, note in results if note == skill.ABSENT]
    rows = [(target["label"], app.short_path(target["folder"]), note) for target, note in results if note != skill.ABSENT]
    widths = [max([len(row[column]) for row in rows] + [0]) for column in (0, 1)]
    for label, folder, note in rows:
        print(f"  {label.ljust(widths[0])}  {folder.ljust(widths[1])}  {note}")
    if absent:
        print(f"\nNot on this computer: {', '.join(absent)}")


def cmd_skill(args):
    action = args.action or "status"
    try:
        only = skill.parse_only(getattr(args, "only", None))
    except ValueError as error:
        print(f"--only: {error}")
        return 2
    if action == "install":
        if not skill.source_ok():
            print(f"There is no handoff SKILL.md next to this copy ({skill.SKILL_DIR}).\n"
                  "Run it from the cloned repository or from an installed copy of the skill.")
            return 1
        version = skill.frontmatter(skill.SKILL_DIR).get("version")
        print(f"handoff skill {version}" + (" - dry run, nothing is changed" if args.dry_run else "") + "\n")
        results = skill.install(only, args.dry_run)
        show(results)
        done = [target for target, note in results if note.startswith(("installed", "updated", "reinstalled"))]
        if done and not args.dry_run:
            copy = next((target for target in done if target["key"] == "agents"), done[0])["folder"]
            print("\nDone. Open a new session in any of these CLIs and say \"save progress\" or \"continue\".")
            print("Call it by name: /handoff in Claude Code, Cursor, Copilot CLI and Qwen Code; $handoff in Codex.")
            print("Update: run the installer again.")
            print(f'Remove: {PYTHON} "{copy / "scripts" / "handoff.py"}" skill uninstall')
        return 1 if any(note.startswith("failed") for _, note in results) else 0
    if action == "uninstall":
        results = skill.uninstall(only)
        if results:
            show(results)
        else:
            print("The handoff skill is not in any CLI's skills folder.")
        return 0
    if action == "zip":
        path = skill.make_zip(args.out)
        print(f"Wrote {path}")
        print("It holds a top-level handoff/ folder, the layout skill uploads expect (claude.ai, skill marketplaces).")
        return 0
    this = skill.frontmatter(skill.SKILL_DIR).get("version") if skill.source_ok() else None
    print(f"This copy:  {app.short_path(skill.SKILL_DIR)}" + (f" (version {this})" if this else " (not a skill folder)"))
    print()
    show([(target, version or ("not installed" if target["found"] else skill.ABSENT))
          for target, version in skill.status()])
    print(f"\nInstall or update: {prog() if prog().endswith('install.py') else prog() + ' skill install'}")
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
    print(f"HANDOFF.md files in your projects are kept. The watcher's own files are in {system.APP_DIR}.")
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog=prog(), epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Writes HANDOFF.md from your coding agents' session logs and git, so the work survives "
                    "context limits, credit limits and crashes, and any other agent can continue it.")
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
    now.add_argument("--tool", type=tool_arg, metavar="AGENT",
                     help=f"only this agent's sessions: {', '.join(sources.MODULES)}")
    now.add_argument("--repo-only", action="store_true",
                     help="write only the git facts, for an agent whose session logs handoff can't read")
    listing = commands.add_parser("sessions", help="this folder's sessions from every agent, newest first")
    listing.add_argument("folder", nargs="?", help="project folder (default: the current folder)")
    listing.add_argument("--tool", type=tool_arg, metavar="AGENT", help="only this agent's sessions")
    listing.add_argument("--days", type=int, default=30, help="how far back to look (default 30)")
    listing.add_argument("--limit", type=int, default=5, help="how many sessions to show (default 5)")
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
    skills = commands.add_parser("skill", help="install this skill into your coding CLIs, or package it")
    actions = skills.add_subparsers(dest="action", metavar="action")
    install_skill = actions.add_parser("install", help="copy the skill into the skills folder of every coding CLI found")
    install_skill.add_argument("--only", metavar="CLIS", help=f"comma-separated, from: {', '.join(skill.KEYS)}")
    install_skill.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    uninstall_skill = actions.add_parser("uninstall", help="remove the skill from every CLI's skills folder")
    uninstall_skill.add_argument("--only", metavar="CLIS", help="comma-separated, as for install")
    actions.add_parser("status", help="where the skill is installed, and which version")
    zip_skill = actions.add_parser("zip", help="package the skill as a .zip, for uploading it")
    zip_skill.add_argument("--out", default="handoff-skill.zip", help="file to write (default handoff-skill.zip)")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handlers = {"status": cmd_status, "now": cmd_now, "sessions": cmd_sessions, "watch": cmd_watch,
                "start": cmd_start, "stop": cmd_stop, "autostart": cmd_autostart, "install": cmd_install,
                "uninstall": cmd_uninstall, "dashboard": cmd_dashboard, "skill": cmd_skill}
    return handlers[args.command](args) or 0
