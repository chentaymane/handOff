import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from handoff import app, dashboard, sources


class DashboardTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.project = Path(folder.name).resolve()
        (self.project / "HANDOFF.md").write_text("# HANDOFF: demo\n", encoding="utf-8")
        row = {"folder": str(self.project), "name": self.project.name, "tool": "Codex", "source": "codex"}
        for target, name, value in ((app, "overview", lambda days=7, limit=12: [row]),
                                    (app, "write_now", lambda folder: (True, f"Wrote {folder}"))):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.server = dashboard.make_server(0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, body=None, headers=None, host=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = dict(headers or {})
        headers["Host"] = host or f"127.0.0.1:{self.port}"
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, data

    def post(self, path, body, **extra):
        headers = {"Content-Type": "application/json", "X-Handoff": "1"}
        headers.update(extra)
        return self.request("POST", path, body, headers)

    def test_page_and_status(self):
        status, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<title>handoff dashboard</title>", page)
        status, data = self.request("GET", "/api/status?days=3")
        data = json.loads(data)
        self.assertEqual((status, data["days"]), (200, 3))
        self.assertEqual([tool["label"] for tool in data["tools"]],
                         [module.LABEL for module in sources.MODULES.values()])
        self.assertEqual(data["sessions"][0]["name"], self.project.name)

    def test_reads_and_writes_only_known_folders(self):
        status, data = self.request("GET", "/api/handoff?folder=" + str(self.project))
        self.assertEqual((status, json.loads(data)["text"]), (200, "# HANDOFF: demo\n"))
        self.assertEqual(self.request("GET", "/api/handoff?folder=/etc")[0], 404)
        status, data = self.post("/api/now", {"folder": str(self.project)})
        self.assertEqual((status, json.loads(data)["ok"]), (200, True))
        self.assertEqual(self.post("/api/now", {"folder": "/etc"})[0], 404)

    def test_other_sites_are_refused(self):
        self.assertEqual(self.request("GET", "/api/status", host="evil.example:80")[0], 403)
        # a plain form post from another page: no custom header, not JSON
        self.assertEqual(self.request("POST", "/api/now", {"folder": str(self.project)},
                                      {"Content-Type": "text/plain"})[0], 403)
        self.assertEqual(self.post("/api/watcher", {"action": "explode"})[0], 400)


if __name__ == "__main__":
    unittest.main()
