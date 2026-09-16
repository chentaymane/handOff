import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from handoff.session import iso_from_ms
from handoff.sources import cursor, gemini, opencode

PROJECT = r"C:\work\scraper" if os.name == "nt" else "/work/scraper"


class TempFolder(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def patch(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)


class GeminiTest(TempFolder):
    def setUp(self):
        super().setUp()
        root = self.folder / ".gemini"
        self.patch(gemini, "ROOT", root)
        self.log = root / "tmp" / "scraper" / "chats" / "session-2026-09-16T09-00-g1.jsonl"
        self.log.parent.mkdir(parents=True)
        (root / "projects.json").write_text(json.dumps({"projects": {PROJECT: "scraper"}}), encoding="utf-8")
        records = [
            {"sessionId": "g1", "projectHash": "abc", "startTime": "2026-09-16T09:00:00.000Z",
             "lastUpdated": "2026-09-16T09:00:00.000Z", "kind": "main"},
            {"id": "m1", "timestamp": "2026-09-16T09:00:01.000Z", "type": "user",
             "content": [{"text": "Build a CSV exporter"}]},
            {"id": "m2", "timestamp": "2026-09-16T09:00:05.000Z", "type": "gemini", "content": "Exporter drafted.",
             "model": "gemini-3-pro", "tokens": {"input": 400000, "output": 2000, "cached": 0, "total": 402000},
             "toolCalls": [
                 {"id": "t1", "name": "write_file", "args": {"file_path": PROJECT + os.sep + "export.py"},
                  "status": "success"},
                 {"id": "t2", "name": "run_shell_command", "args": {"command": "pytest"}, "status": "error",
                  "resultDisplay": "2 failed"},
                 {"id": "t3", "name": "write_todos", "status": "success", "args": {"todos": [
                     {"description": "Write exporter", "status": "completed"},
                     {"description": "Fix tests", "status": "in_progress"}]}}]},
            {"id": "m3", "timestamp": "2026-09-16T09:05:00.000Z", "type": "user", "content": "oops, wrong prompt"},
            {"$rewindTo": "m3"},
            {"id": "m4", "timestamp": "2026-09-16T09:10:00.000Z", "type": "error",
             "content": "Quota exceeded for quota metric 'Gemini requests per day' (RESOURCE_EXHAUSTED)"},
        ]
        self.log.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
        self.session = gemini.read(self.log)

    def test_requests_reply_and_rewind(self):
        self.assertEqual(self.session.asks, ["Build a CSV exporter"])
        self.assertEqual((self.session.agent_last, self.session.model), ("Exporter drafted.", "gemini-3-pro"))

    def test_folder_comes_from_the_project_registry(self):
        self.assertEqual(self.session.cwd, PROJECT)
        self.assertEqual(gemini.folder(self.log), PROJECT)
        self.assertEqual([ref for ref, _ in gemini.discover()], [str(self.log)])

    def test_tools_plan_context_and_quota(self):
        session = self.session
        self.assertEqual(session.files, {PROJECT + os.sep + "export.py": "written"})
        self.assertEqual(session.commands, ["pytest"])
        self.assertEqual(session.plan, [("Write exporter", "completed"), ("Fix tests", "in_progress")])
        self.assertEqual((session.context_tokens, session.context_window), (402000, gemini.WINDOW))
        self.assertIn("run_shell_command: 2 failed", session.errors)
        self.assertTrue(session.limit_hit)
        self.assertEqual((session.started, session.updated), ("2026-09-16T09:00:00.000Z", "2026-09-16T09:10:00.000Z"))

    def test_older_single_file_format(self):
        legacy = self.log.with_name("session-old.json")
        legacy.write_text(json.dumps({"sessionId": "old", "startTime": "2026-01-01T00:00:00.000Z", "messages": [
            {"id": "a", "timestamp": "2026-01-01T00:00:01.000Z", "type": "user", "content": "Old request"},
            {"id": "b", "timestamp": "2026-01-01T00:00:02.000Z", "type": "gemini", "content": "Old reply"}]}),
            encoding="utf-8")
        session = gemini.read(legacy)
        self.assertEqual((session.asks, session.agent_last, session.id), (["Old request"], "Old reply", "old"))


class CursorTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.db = self.folder / "state.vscdb"
        chat = {"composerId": "c1", "name": "Fix upload", "createdAt": 1789000000000, "lastUpdatedAt": 1789000600000,
                "workspaceIdentifier": {"id": "w", "uri": {"fsPath": PROJECT}},
                "modelConfig": {"modelName": "composer-2.5"}, "contextTokensUsed": 77561, "contextTokenLimit": 200000,
                "fullConversationHeadersOnly": [{"bubbleId": key, "type": 1 if key == "b1" else 2}
                                                for key in ("b1", "b2", "b3", "b4", "b5")],
                "todos": [{"content": "Fix IndexedDB error", "status": "completed"},
                          {"content": "Retest upload", "status": "pending"}]}
        bubbles = {
            "b1": {"type": 1, "text": "Fix the IndexedDB error"},
            "b2": {"type": 2, "text": "", "toolFormerData": {
                "name": "edit_file_v2", "status": "completed",
                "params": json.dumps({"relativeWorkspacePath": PROJECT + os.sep + "kit-db.js"})}},
            "b3": {"type": 2, "text": "", "toolFormerData": {
                "name": "run_terminal_command_v2", "status": "error",
                "params": json.dumps({"command": "node --check popup.js"}),
                "error": json.dumps({"clientVisibleErrorMessage": "Command failed to execute"})}},
            "b4": {"type": 2, "text": "", "toolFormerData": {
                "name": "delete_file", "status": "completed",
                "params": json.dumps({"relativeWorkspacePath": PROJECT + os.sep + "old.js"})}},
            "b5": {"type": 2, "text": "Fixed the store. Retest the upload."},
        }
        rows = [("composerData:c1", json.dumps(chat)), ("composerData:draft", json.dumps({"composerId": "draft"}))]
        rows += [(f"bubbleId:c1:{key}", json.dumps(value)) for key, value in bubbles.items()]
        connection = sqlite3.connect(self.db)
        connection.execute("create table cursorDiskKV (key text unique on conflict replace, value blob)")
        connection.executemany("insert into cursorDiskKV values (?, ?)", rows)
        connection.commit()
        connection.close()
        self.patch(cursor, "DB", self.db)
        self.patch(cursor, "TRANSCRIPTS", self.folder / "no-transcripts")
        self.patch(cursor, "_cache", {})
        self.ref = f"{self.db}#c1"

    def test_discovers_chats_with_their_folder(self):
        self.assertEqual(cursor.discover(), [(self.ref, 1789000600.0)])
        self.assertEqual(cursor.folder(self.ref), PROJECT)

    def test_reads_the_conversation(self):
        session = cursor.read(self.ref)
        self.assertEqual(session.asks, ["Fix the IndexedDB error"])
        self.assertEqual(session.agent_last, "Fixed the store. Retest the upload.")
        self.assertEqual((session.cwd, session.model), (PROJECT, "composer-2.5"))
        self.assertEqual((session.context_tokens, session.context_window), (77561, 200000))
        self.assertEqual(session.files, {PROJECT + os.sep + "kit-db.js": "edited", PROJECT + os.sep + "old.js": "deleted"})
        self.assertEqual(session.commands, ["node --check popup.js"])
        self.assertEqual(session.errors, ["run_terminal_command_v2: Command failed to execute"])
        self.assertEqual(session.plan, [("Fix IndexedDB error", "completed"), ("Retest upload", "pending")])
        self.assertEqual(session.updated, iso_from_ms(1789000600000))


class OpenCodeTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.db = self.folder / "opencode.db"
        connection = sqlite3.connect(self.db)
        connection.executescript("""
            create table session (id text primary key, project_id text, parent_id text, directory text, title text,
                                  time_created integer, time_updated integer, model text);
            create table message (id text primary key, session_id text, time_created integer, time_updated integer,
                                  data text);
            create table part (id text primary key, message_id text, session_id text, time_created integer,
                               time_updated integer, data text);
            create table todo (session_id text, content text, status text, priority text, position integer,
                               time_created integer, time_updated integer);
        """)
        connection.execute("insert into session values ('s1', 'p', null, ?, 'Scraper', 1789000000000, 1789000900000, ?)",
                           (PROJECT, json.dumps({"id": "big-pickle", "providerID": "opencode"})))
        connection.execute("insert into session values ('s2', 'p', 's1', ?, 'Explore', 1789000000000, 1789000950000, null)",
                           (PROJECT,))
        messages = [
            ("m1", 1, {"role": "user"}),
            ("m2", 2, {"role": "assistant", "modelID": "big-pickle"}),
            ("m3", 3, {"role": "assistant", "error": {"name": "APIError", "data": {
                "message": "Rate limit reached for requests", "statusCode": 429}}}),
        ]
        connection.executemany("insert into message values (?, 's1', ?, ?, ?)",
                               [(key, time, time, json.dumps(data)) for key, time, data in messages])
        parts = [
            ("p1", "m1", 1, {"type": "text", "text": "Scrape the product pages"}),
            ("p2", "m1", 2, {"type": "text", "text": "<system-reminder>ignore</system-reminder>", "synthetic": True}),
            ("p3", "m2", 3, {"type": "tool", "tool": "write", "state": {
                "status": "completed", "input": {"filePath": PROJECT + os.sep + "scrape.py"}}}),
            ("p4", "m2", 4, {"type": "tool", "tool": "bash", "state": {
                "status": "error", "input": {"command": "python scrape.py"}, "error": "ModuleNotFoundError: requests"}}),
            ("p5", "m2", 5, {"type": "text", "text": "Script written; it needs requests installed."}),
            ("p6", "m2", 6, {"type": "step-finish", "tokens": {
                "total": 26095, "input": 0, "output": 258, "cache": {"write": 25837, "read": 0}}}),
        ]
        connection.executemany("insert into part values (?, ?, 's1', ?, ?, ?)",
                               [(key, message, time, time, json.dumps(data)) for key, message, time, data in parts])
        connection.executemany("insert into todo values ('s1', ?, ?, 'high', ?, 1, 1)",
                               [("Write scraper", "completed", 0), ("Install requests", "in_progress", 1)])
        connection.commit()
        connection.close()
        self.patch(opencode, "DB", self.db)
        self.patch(opencode, "_cache", {})
        self.ref = f"{self.db}#s1"

    def test_discovers_top_level_sessions_only(self):
        self.assertEqual(opencode.discover(), [(self.ref, 1789000900.0)])
        self.assertEqual(opencode.folder(self.ref), PROJECT)

    def test_reads_the_session(self):
        session = opencode.read(self.ref)
        self.assertEqual(session.asks, ["Scrape the product pages"])
        self.assertEqual(session.agent_last, "Script written; it needs requests installed.")
        self.assertEqual((session.cwd, session.model), (PROJECT, "big-pickle"))
        self.assertEqual(session.files, {PROJECT + os.sep + "scrape.py": "written"})
        self.assertEqual(session.commands, ["python scrape.py"])
        self.assertEqual(session.errors, ["bash: ModuleNotFoundError: requests", "Rate limit reached for requests"])
        self.assertTrue(session.limit_hit)
        self.assertEqual(session.context_tokens, 26095)
        self.assertEqual(session.plan, [("Write scraper", "completed"), ("Install requests", "in_progress")])


class CursorTranscriptTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.project = self.folder / "my app"
        self.project.mkdir()
        projects = self.folder / "cursor-projects"
        self.log = projects / cursor.slug_for(self.project) / "agent-transcripts" / "t1" / "t1.jsonl"
        self.log.parent.mkdir(parents=True)
        lines = [
            {"role": "user", "message": {"content": [{"type": "text", "text": "<user_query>\nAdd dark mode\n</user_query>"}]}},
            {"role": "assistant", "message": {"content": [
                {"type": "text", "text": "Adding a theme toggle.\n\n[REDACTED]"},
                {"type": "tool_use", "name": "Write", "input": {"path": str(self.project / "theme.css"), "contents": "x"}},
                {"type": "tool_use", "name": "StrReplace", "input": {"path": str(self.project / "app.js"),
                                                                     "old_string": "a", "new_string": "b"}},
                {"type": "tool_use", "name": "Shell", "input": {"command": "npm run build"}},
                {"type": "tool_use", "name": "TodoWrite", "input": {"todos": [
                    {"id": "1", "content": "Toggle", "status": "completed"},
                    {"id": "2", "content": "Persist choice", "status": "pending"}]}}]}},
            {"type": "turn_ended", "status": "success"},
            {"role": "user", "message": {"content": [{"type": "text", "text": "<user_query>\nnow save it\n</user_query>"}]}},
            {"type": "turn_ended", "status": "error", "error": "You've hit your usage limit Get Cursor Pro for more Agent usage."},
        ]
        self.log.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
        self.patch(cursor, "TRANSCRIPTS", projects)
        self.patch(cursor, "DB", self.folder / "no-cursor-database" / "state.vscdb")
        self.patch(cursor, "_cache", {})

    def test_discovers_the_transcript_and_resolves_its_folder(self):
        self.assertEqual([ref for ref, _ in cursor.discover()], [str(self.log)])
        self.assertEqual(os.path.normcase(cursor.folder(str(self.log))), os.path.normcase(str(self.project)))

    def test_reads_messages_tools_and_the_usage_limit(self):
        session = cursor.read(str(self.log))
        self.assertEqual(session.asks, ["Add dark mode", "now save it"])
        self.assertEqual(session.agent_last, "Adding a theme toggle.")
        self.assertEqual(session.files, {str(self.project / "theme.css"): "written", str(self.project / "app.js"): "edited"})
        self.assertEqual(session.commands, ["npm run build"])
        self.assertEqual(session.plan, [("Toggle", "completed"), ("Persist choice", "pending")])
        self.assertTrue(session.limit_hit)
        self.assertIn("You've hit your usage limit", session.errors[-1])
        self.assertEqual(os.path.normcase(session.cwd), os.path.normcase(str(self.project)))


if __name__ == "__main__":
    unittest.main()
