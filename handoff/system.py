"""Where the app keeps its files, plus the OS-specific parts: notifications, background, autostart."""

import datetime
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(os.environ.get("HANDOFF_HOME") or Path.home() / ".handoff")
LOG_FILE = APP_DIR / "handoff.log"
PID_FILE = APP_DIR / "watch.pid"
STATE_FILE = APP_DIR / "state.json"
PACKAGE_PARENT = Path(__file__).resolve().parent.parent  # lets `-m handoff` work from a git clone
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
POWERSHELL_APP_ID = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"


def log(message):
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            os.replace(LOG_FILE, LOG_FILE.with_name(LOG_FILE.name + ".1"))
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  {message}\n")
    except OSError:
        pass


def load_json(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def save_json(path, data):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        pass


# ---- notifications -----------------------------------------------------------------

def notify(title, body):
    """Show a desktop notification. Best effort: never raises, never blocks for long."""
    try:
        system = platform.system()
        if system == "Windows":
            _notify_windows(title, body)
        elif system == "Darwin":
            script = f"display notification {json.dumps(body)} with title {json.dumps(title)}"
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", title, body], capture_output=True, timeout=10)
    except Exception:
        pass


def _notify_windows(title, body):
    def xml(text):
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    toast = (f"<toast><visual><binding template='ToastGeneric'><text>{xml(title)}</text>"
             f"<text>{xml(body)}</text></binding></visual></toast>")
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
        "$doc = New-Object Windows.Data.Xml.Dom.XmlDocument; $doc.LoadXml($env:HANDOFF_TOAST);"
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $doc;"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{POWERSHELL_APP_ID}').Show($toast)"
    )
    # Windows PowerShell 5.1 still loads WinRT types; PowerShell 7 can't, so call powershell.exe explicitly.
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                   env=dict(os.environ, HANDOFF_TOAST=toast), capture_output=True, timeout=20,
                   creationflags=NO_WINDOW)


# ---- the background watcher --------------------------------------------------------

def pythonw():
    """The interpreter to run in the background: pythonw.exe on Windows, so no console window opens."""
    executable = Path(sys.executable)
    if os.name == "nt":
        windowless = executable.with_name("pythonw.exe")
        if windowless.exists():
            return str(windowless)
    return str(executable)


def pid_alive(pid):
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def watcher_pid():
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if pid_alive(pid) else None


def write_pid():
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_pid():
    try:
        if PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink()
    except OSError:
        pass


def start_background():
    """Start `handoff watch` detached from this terminal. Returns (pid, started_now)."""
    running = watcher_pid()
    if running:
        return running, False
    options = dict(cwd=str(PACKAGE_PARENT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        options["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen([pythonw(), "-m", "handoff", "watch"], **options)
    return process.pid, True


def stop_background():
    pid = watcher_pid()
    if not pid:
        return None
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NO_WINDOW)
    else:
        os.kill(pid, signal.SIGTERM)
    try:
        PID_FILE.unlink()
    except OSError:
        pass
    return pid


# ---- start at login ----------------------------------------------------------------

def autostart_path():
    system = platform.system()
    if system == "Windows":
        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        return startup / "handoff-watch.vbs"
    if system == "Darwin":
        return Path.home() / "Library" / "LaunchAgents" / "io.github.handoff.watch.plist"
    return Path.home() / ".config" / "autostart" / "handoff-watch.desktop"


def set_autostart(enabled):
    """Create or remove the login item. Returns its path."""
    path = autostart_path()
    if not enabled:
        if path.exists():
            path.unlink()
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    if system == "Windows":
        executable = pythonw().replace('"', '""')
        folder = str(PACKAGE_PARENT).replace('"', '""')
        script = ('Set shell = CreateObject("WScript.Shell")\n'  # text mode turns \n into \r\n on Windows
                  f'shell.CurrentDirectory = "{folder}"\n'
                  f'shell.Run """{executable}"" -m handoff watch", 0, False\n')
        path.write_text(script, encoding="mbcs")
    elif system == "Darwin":
        def xml(text):
            return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>\n'
            '<key>Label</key><string>io.github.handoff.watch</string>\n'
            f'<key>ProgramArguments</key><array><string>{xml(sys.executable)}</string>'
            '<string>-m</string><string>handoff</string><string>watch</string></array>\n'
            f'<key>WorkingDirectory</key><string>{xml(PACKAGE_PARENT)}</string>\n'
            '<key>RunAtLoad</key><true/>\n'
            '</dict></plist>\n', encoding="utf-8")
    else:
        path.write_text(
            "[Desktop Entry]\nType=Application\nName=handoff watcher\n"
            f'Exec="{sys.executable}" -m handoff watch\nPath={PACKAGE_PARENT}\n'
            "NoDisplay=true\nX-GNOME-Autostart-enabled=true\n", encoding="utf-8")
    return path
