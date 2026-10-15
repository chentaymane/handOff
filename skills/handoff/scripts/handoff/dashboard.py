"""A local web dashboard: `handoff dashboard` serves it on http://127.0.0.1:7788 (this computer only)."""

import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, app, render, sources, system

PAGE = Path(__file__).with_name("dashboard.html")
PORT = 7788
MAX_BODY = 10_000


def tools():
    return [{"source": name, "label": module.LABEL} for name, module in sources.MODULES.items()]


def status(days):
    return {"version": __version__, "watcher": app.watcher_state(), "tools": tools(),
            "sessions": app.overview(days, 40), "days": days}


def known_folder(folder):
    """Only folders an agent has worked in may be read or written through the dashboard."""
    wanted = str(Path(folder).resolve()) if folder else ""
    return any(row["folder"] == wanted for row in app.overview(90, 200)) and wanted


class Handler(BaseHTTPRequestHandler):
    server_version = f"handoff/{__version__}"

    def log_message(self, *args):  # keep the terminal quiet
        pass

    # ---- safety: this server may run commands on your machine, so only this machine's pages may use it

    def allowed_host(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def send(self, code, body, kind="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.allowed_host():
            return self.send(HTTPStatus.FORBIDDEN, {"error": "forbidden host"})
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            return self.send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/status":
            try:
                days = max(1, min(90, int((query.get("days") or ["7"])[0])))
            except ValueError:
                days = 7
            return self.send(HTTPStatus.OK, status(days))
        if url.path == "/api/handoff":
            folder = known_folder((query.get("folder") or [""])[0])
            if not folder:
                return self.send(HTTPStatus.NOT_FOUND, {"error": "unknown folder"})
            path = Path(folder) / render.HANDOFF_NAME
            text = render.read_text(path)[0] if path.exists() else None
            return self.send(HTTPStatus.OK, {"folder": folder, "path": str(path), "text": text})
        return self.send(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self):
        # A custom header and a JSON body can't be sent by another website without a CORS preflight,
        # which this server never approves.
        if not self.allowed_host() or self.headers.get("X-Handoff") != "1" \
                or not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, MAX_BODY)) or b"{}") if length <= MAX_BODY else None
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self.send(HTTPStatus.BAD_REQUEST, {"error": "bad request"})
        path = urlparse(self.path).path
        if path == "/api/now":
            folder = known_folder(body.get("folder"))
            if not folder:
                return self.send(HTTPStatus.NOT_FOUND, {"ok": False, "message": "Unknown folder."})
            ok, message = app.write_now(folder)
            return self.send(HTTPStatus.OK, {"ok": ok, "message": message})
        if path == "/api/watcher":
            if body.get("action") == "start":
                pid, started = system.start_background()
                message = f"Watcher started (pid {pid})." if started else f"Watcher already running (pid {pid})."
            elif body.get("action") == "stop":
                pid = system.stop_background()
                message = f"Watcher stopped (pid {pid})." if pid else "The watcher was not running."
            else:
                return self.send(HTTPStatus.BAD_REQUEST, {"error": "unknown action"})
            return self.send(HTTPStatus.OK, {"ok": True, "message": message})
        if path == "/api/autostart":
            where = system.set_autostart(bool(body.get("on")))
            return self.send(HTTPStatus.OK, {"ok": True, "message": f"Autostart {'on' if body.get('on') else 'off'}"
                                                                      f" ({where})."})
        return self.send(HTTPStatus.NOT_FOUND, {"error": "not found"})


def make_server(port=PORT, tries=10):
    """Bind to this computer only, on `port` or the next free one."""
    error = None
    for candidate in range(port, port + tries):
        try:
            return ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
        except OSError as exc:
            error = exc
    raise error


def serve(port=PORT, open_browser=True):
    server = make_server(port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Dashboard: {url}  (only reachable from this computer; Ctrl+C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        server.server_close()
    return 0
