import json
import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from handoff import sources, system, watch
from handoff.sources import Session


def busy(cwd):
    return Session(tool="Codex", path=Path("x"), cwd=str(cwd), files={"a.py": "edited"})


class TempFolder(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.project = self.base / "project"
        self.project.mkdir()
        self.patch(watch, "TEMP_DIR", str(self.base / "elsewhere"))

    def patch(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)


class SkipReasonTest(TempFolder):
    def test_project_folder_is_fine(self):
        self.assertIsNone(watch.skip_reason(busy(self.project), self.project))

    def test_home_folder(self):
        self.assertEqual(watch.skip_reason(busy(Path.home()), Path.home()), "home folder or drive root")

    def test_temporary_folder(self):
        self.patch(watch, "TEMP_DIR", str(self.base))
        self.assertEqual(watch.skip_reason(busy(self.project), self.project), "temporary folder")

    def test_opt_out_file(self):
        (self.project / ".nohandoff").touch()
        self.assertEqual(watch.skip_reason(busy(self.project), self.project), ".nohandoff file")

    def test_too_little_activity(self):
        quiet = Session(tool="Codex", path=Path("x"), cwd=str(self.project), asks=["hi"])
        self.assertEqual(watch.skip_reason(quiet, self.project), "too little activity yet")

    def test_missing_folder(self):
        self.assertEqual(watch.skip_reason(busy(self.base / "gone"), self.base / "gone"), "folder no longer exists")


class AlertTest(unittest.TestCase):
    def test_levels(self):
        session = Session(tool="Codex", path=Path("x"))
        self.assertEqual(watch.alerts(session), [])
        session.limit_percent = 87
        self.assertEqual([key for key, _ in watch.alerts(session)], ["limit-80"])
        session.limit_percent, session.context_tokens, session.context_window = 96, 90, 100
        self.assertEqual([key for key, _ in watch.alerts(session)], ["limit-95", "context-85"])
        session.limit_hit = True
        self.assertEqual(watch.alerts(session)[0][0], "limit-hit")


class WatcherTest(TempFolder):
    def setUp(self):
        super().setUp()
        day = date.today()
        self.log = self.base / "codex" / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}" / "rollout-1.jsonl"
        self.log.parent.mkdir(parents=True)
        self.alerts = []
        self.patch(sources.codex, "ROOT", self.base / "codex")
        only_codex = mock.patch.dict(sources.MODULES, {"codex": sources.codex}, clear=True)
        only_codex.start()
        self.addCleanup(only_codex.stop)
        self.patch(system, "STATE_FILE", self.base / "state.json")
        self.patch(system, "LOG_FILE", self.base / "handoff.log")
        self.patch(system, "notify", lambda title, body: self.alerts.append(title))

    def append(self, *entries):
        with open(self.log, "a", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")

    def test_writes_at_once_on_alert_and_again_when_quiet(self):
        cwd = str(self.project)
        self.append(
            {"type": "session_meta", "payload": {"id": "s", "cwd": cwd}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "Ship the uploader"}},
            {"type": "event_msg", "payload": {"type": "patch_apply_end",
                                              "changes": {cwd + os.sep + "up.js": {"type": "add"}}}},
            {"type": "event_msg", "payload": {"type": "agent_message", "message": "First draft done."}},
            {"type": "event_msg", "payload": {"type": "token_count", "info": {},
                                              "rate_limits": {"primary": {"used_percent": 88.0,
                                                                          "window_minutes": 300}}}},
        )
        watcher = watch.Watcher(echo=lambda message: None)
        watcher.started = 0
        handoff = self.project / "HANDOFF.md"
        now = time.time()

        watcher.tick(now)  # still busy, but at 88% usage: write right away and alert once
        self.assertIn("88% used of the 5-hour window", handoff.read_text(encoding="utf-8"))
        self.assertEqual(len(self.alerts), 1)

        watcher.tick(now + 60)  # quiet: final write, the alert is not repeated
        self.assertEqual(len(self.alerts), 1)

        self.append({"type": "event_msg", "payload": {"type": "agent_message", "message": "Tests pass now."}})
        watcher.tick(now + 120)  # busy again, nothing urgent: wait
        self.assertNotIn("Tests pass now.", handoff.read_text(encoding="utf-8"))
        watcher.tick(now + 200)  # quiet: write
        self.assertIn("Tests pass now.", handoff.read_text(encoding="utf-8"))
        self.assertEqual(len(self.alerts), 1)

    def test_ignores_activity_from_before_it_started(self):
        self.append({"type": "session_meta", "payload": {"id": "s", "cwd": str(self.project)}},
                    {"type": "event_msg", "payload": {"type": "patch_apply_end",
                                                      "changes": {"x.js": {"type": "add"}}}})
        watcher = watch.Watcher(echo=lambda message: None)
        watcher.started = time.time() + 3600
        watcher.tick(time.time() + 7200)
        self.assertFalse((self.project / "HANDOFF.md").exists())


if __name__ == "__main__":
    unittest.main()
