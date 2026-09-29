import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from handoff import render, sources, system
from handoff.session import Session
from handoff.sources import aider, claude, codebuff, copilot, qwen

PROJECT = r"C:\work\notes" if os.name == "nt" else "/work/notes"


def write_jsonl(path, entries):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    return path


class TempFolder(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def patch(self, target, name, value):
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)


class ClaudeExtrasTest(TempFolder):
    LOG = [
        {"type": "user", "cwd": PROJECT, "timestamp": "2026-09-29T12:00:00.000Z", "message": {"role": "user", "content": [
            {"type": "text", "text": "<ide_opened_file>The user opened the file x.go in the IDE.</ide_opened_file>\n"
                                     "Add an avatar to the register form"}]}},
        {"type": "ai-title", "aiTitle": "Register form avatar"},
        {"type": "assistant", "cwd": PROJECT, "timestamp": "2026-09-29T12:01:00.000Z",
         "message": {"model": "claude-opus-5-5[1m]", "content": [{"type": "text", "text": "Avatar upload added."}]}},
        {"type": "assistant", "cwd": PROJECT, "timestamp": "2026-09-29T12:02:00.000Z", "isApiErrorMessage": False,
         "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "No response requested."}]}},
        {"type": "system", "subtype": "away_summary", "timestamp": "2026-09-29T12:03:00.000Z",
         "content": "You wanted an avatar on register; it works. Next, test the upload. (disable recaps in /config)"},
        {"type": "assistant", "cwd": PROJECT, "timestamp": "2026-09-29T12:04:00.000Z", "isApiErrorMessage": True,
         "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "You've hit your limit · resets 5pm"}]}},
    ]

    def test_ide_tags_titles_recaps_and_placeholders(self):
        session = claude.read(write_jsonl(self.folder / "s.jsonl", self.LOG))
        self.assertEqual(session.asks, ["Add an avatar to the register form"])
        self.assertEqual(session.title, "Register form avatar")
        self.assertEqual(session.agent_last, "Avatar upload added.")
        self.assertEqual(session.summary, "You wanted an avatar on register; it works. Next, test the upload.")
        self.assertEqual((session.model, session.context_window), ("claude-opus-5-5[1m]", 1_000_000))
        self.assertTrue(session.limit_hit)

    def test_a_new_request_retires_the_recap_and_a_given_name_wins(self):
        log = self.LOG + [
            {"type": "custom-title", "customTitle": "avatar work"},
            {"type": "ai-title", "aiTitle": "Something else"},
            {"type": "user", "cwd": PROJECT, "timestamp": "2026-09-29T13:00:00.000Z",
             "message": {"role": "user", "content": "Now crop it to a circle"}}]
        session = claude.read(write_jsonl(self.folder / "s.jsonl", log))
        self.assertEqual((session.summary, session.title), ("", "avatar work"))


class QwenTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.patch(qwen, "ROOT", self.folder / ".qwen")
        part = {"role": "model"}
        self.log = write_jsonl(self.folder / ".qwen" / "tmp" / "a1b2" / "chats" / "q1.jsonl", [
            {"uuid": "1", "sessionId": "q1", "timestamp": "2026-09-29T09:00:00.000Z", "type": "user", "cwd": PROJECT,
             "message": {"role": "user", "parts": [{"text": "Add markdown export"}]}},
            {"uuid": "2", "sessionId": "q1", "timestamp": "2026-09-29T09:00:05.000Z", "type": "assistant",
             "cwd": PROJECT, "model": "qwen3-coder-plus", "contextWindowSize": 131072,
             "usageMetadata": {"promptTokenCount": 90000, "candidatesTokenCount": 1000, "totalTokenCount": 91000},
             "message": dict(part, parts=[
                 {"text": "thinking...", "thought": True}, {"text": "Export written, tests next."},
                 {"functionCall": {"name": "write_file", "args": {"file_path": PROJECT + "/export.py"}}},
                 {"functionCall": {"name": "run_shell_command", "args": {"command": "pytest -q"}}},
                 {"functionCall": {"name": "todo_write", "args": {"todos": [
                     {"id": "1", "content": "Export", "status": "completed"},
                     {"id": "2", "content": "Tests", "status": "pending"}]}}}])},
            {"uuid": "3", "sessionId": "q1", "timestamp": "2026-09-29T09:00:09.000Z", "type": "tool_result",
             "cwd": PROJECT, "toolCallResult": {"status": "error", "error": {"message": "Rate limit exceeded (429)"}}},
            {"uuid": "4", "sessionId": "q1", "timestamp": "2026-09-29T09:00:10.000Z", "type": "assistant",
             "cwd": PROJECT, "isSidechain": True, "message": dict(part, parts=[{"text": "subagent"}])},
        ])

    def test_reads_the_session(self):
        session = qwen.read(self.log)
        self.assertEqual((session.cwd, session.model), (PROJECT, "qwen3-coder-plus"))
        self.assertEqual(session.asks, ["Add markdown export"])
        self.assertEqual(session.agent_last, "Export written, tests next.")
        self.assertEqual(session.files, {PROJECT + "/export.py": "written"})
        self.assertEqual(session.commands, ["pytest -q"])
        self.assertEqual(session.plan, [("Export", "completed"), ("Tests", "pending")])
        self.assertEqual((session.context_tokens, session.context_window), (91000, 131072))
        self.assertTrue(session.limit_hit)

    def test_discovery_and_folder(self):
        self.assertEqual([ref for ref, _ in qwen.discover()], [str(self.log)])
        self.assertEqual(qwen.folder(self.log), PROJECT)
        self.assertEqual(sources.detect_tool(self.log), "qwen")


class CopilotTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.patch(copilot, "ROOT", self.folder / ".copilot" / "session-state")
        session = self.folder / ".copilot" / "session-state" / "c0ffee"
        self.log = write_jsonl(session / "events.jsonl", [
            {"type": "session.start", "timestamp": "2026-09-29T10:00:00.000Z",
             "data": {"sessionId": "c0ffee", "context": {"cwd": PROJECT}, "selectedModel": "gpt-5.5"}},
            {"type": "user.message", "timestamp": "2026-09-29T10:00:01.000Z", "data": {"content": "Fix the flaky test"}},
            {"type": "tool.execution_start", "timestamp": "2026-09-29T10:00:02.000Z",
             "data": {"toolName": "bash", "arguments": {"command": "npm test"}}},
            {"type": "tool.execution_start", "timestamp": "2026-09-29T10:00:03.000Z",
             "data": {"toolName": "edit", "arguments": {"path": PROJECT + "/test/a.test.js"}}},
            {"type": "tool.execution_start", "timestamp": "2026-09-29T10:00:03.500Z",
             "data": {"toolName": "update_todo", "arguments": {"todos": "- [x] Find the race\n- [ ] Add a retry"}}},
            {"type": "tool.execution_complete", "timestamp": "2026-09-29T10:00:04.000Z",
             "data": {"success": False, "result": {"content": "1 failing"}}},
            {"type": "assistant.message", "timestamp": "2026-09-29T10:00:05.000Z",
             "data": {"content": "The race is fixed; one test still fails."}},
            {"type": "session.usage_info", "timestamp": "2026-09-29T10:00:05.500Z",
             "data": {"currentTokens": 60000, "tokenLimit": 128000}},
            {"type": "session.task_complete", "timestamp": "2026-09-29T10:00:06.000Z",
             "data": {"summary": "Fixed the race in a.test.js", "success": True}},
            {"type": "session.error", "timestamp": "2026-09-29T10:00:07.000Z",
             "data": {"errorType": "rate_limit", "message": "You have exceeded your premium request allowance"}},
        ])
        (session / "workspace.yaml").write_text(f"id: c0ffee\ncwd: {PROJECT}\nsummary: Flaky test fix\n",
                                                encoding="utf-8")

    def test_reads_the_session(self):
        session = copilot.read(self.log)
        self.assertEqual((session.cwd, session.model, session.title), (PROJECT, "gpt-5.5", "Flaky test fix"))
        self.assertEqual(session.asks, ["Fix the flaky test"])
        self.assertEqual(session.agent_last, "The race is fixed; one test still fails.")
        self.assertEqual(session.summary, "Fixed the race in a.test.js")
        self.assertEqual(session.commands, ["npm test"])
        self.assertEqual(session.files, {PROJECT + "/test/a.test.js": "edited"})
        self.assertEqual(session.plan, [("Find the race", "completed"), ("Add a retry", "pending")])
        self.assertEqual((session.context_tokens, session.context_window), (60000, 128000))
        self.assertIn("1 failing", session.errors)
        self.assertTrue(session.limit_hit)

    def test_discovery_and_folder(self):
        self.assertEqual([ref for ref, _ in copilot.discover()], [str(self.log)])
        self.assertEqual(copilot.folder(self.log), PROJECT)
        self.assertEqual(sources.detect_tool(self.log), "copilot")


class CodebuffTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.patch(codebuff, "CONFIG", self.folder / ".config")
        chat = self.folder / ".config" / "manicode" / "projects" / "notes" / "chats" / "2026-09-29T08-30-00.000Z"
        chat.mkdir(parents=True)
        self.log = chat / codebuff.MESSAGES
        self.log.write_text(json.dumps([
            {"id": "1", "variant": "user", "content": "Add tags to notes", "timestamp": "08:30 AM"},
            {"id": "2", "variant": "ai", "content": "", "timestamp": "08:31 AM",
             "metadata": {"usage": {"model": "deepseek-v4-flash", "input_tokens": 30000,
                                    "cache_read_input_tokens": 10000, "output_tokens": 900}},
             "blocks": [
                 {"type": "text", "content": "hmm", "textType": "reasoning"},
                 {"type": "text", "content": "Tags are stored; the UI is next."},
                 {"type": "tool", "toolName": "run_terminal_command", "input": {"command": "npm test"},
                  "output": '{"errorMessage": "2 tests failed"}'},
                 {"type": "tool", "toolName": "write_todos", "input": {"todos": [
                     {"task": "Store tags", "completed": True}, {"task": "Tag UI", "completed": False}]}},
                 {"type": "agent", "agentType": "editor", "blocks": [
                     {"type": "tool", "toolName": "write_file", "input": {"path": "src/tags.ts"}},
                     {"type": "tool", "toolName": "apply_patch", "input": {"operations": [
                         {"type": "update_file", "path": "src/notes.ts", "diff": "..."}]}}]}]},
            {"id": "3", "variant": "error", "content": "Out of credits. Please add more credits.",
             "timestamp": "08:32 AM"},
        ]), encoding="utf-8")
        run_state = {"sessionState": {"fileContext": {"projectRoot": PROJECT, "cwd": PROJECT, "fileTree": []}}}
        (chat / codebuff.RUN_STATE).write_text(json.dumps(run_state), encoding="utf-8")

    def test_reads_the_chat(self):
        session = codebuff.read(self.log)
        self.assertEqual((session.cwd, session.model), (PROJECT, "deepseek-v4-flash"))
        self.assertEqual(session.started, "2026-09-29T08:30:00.000Z")
        self.assertEqual(session.asks, ["Add tags to notes"])
        self.assertEqual(session.agent_last, "Tags are stored; the UI is next.")
        self.assertEqual(session.commands, ["npm test"])
        self.assertEqual(session.plan, [("Store tags", "completed"), ("Tag UI", "pending")])
        self.assertEqual(session.files, {os.path.join(PROJECT, "src/tags.ts"): "written",
                                         os.path.join(PROJECT, "src/notes.ts"): "edited"})
        self.assertEqual(session.context_tokens, 40900)
        self.assertTrue(any("2 tests failed" in error for error in session.errors))
        self.assertTrue(session.limit_hit)

    def test_discovery_and_folder(self):
        self.assertEqual([ref for ref, _ in codebuff.discover()], [str(self.log)])
        self.assertEqual(codebuff.folder(self.log), PROJECT)
        self.assertEqual(sources.detect_tool(self.log), "codebuff")


AIDER_HISTORY = """
# aider chat started at 2026-09-28 18:00:00

> aider --model sonnet
> Main model: claude-sonnet-5 with diff edit format

#### make the README shorter

Done.

# aider chat started at 2026-09-29 09:00:00

> aider --model sonnet
> Main model: claude-sonnet-5 with diff edit format
> Git repo: .git with 12 files

#### add a --json flag to the cli
#### and document it

I'll add the flag in cli.py.

cli.py
```python
<<<<<<< SEARCH
=======
>>>>>>> REPLACE
```

> Tokens: 12k sent, 1.5k received. Cost: $0.05 message, $0.05 session.
> Applied edit to cli.py
> Commit 1a2b3c4 feat: add --json flag

#### /run pytest -q

> Running pytest -q
> litellm.RateLimitError: AnthropicException - rate limit exceeded

# aider chat started at 2026-09-29 10:00:00

> aider --model sonnet
"""


class AiderTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.project = self.folder / "code" / "tool"
        self.project.mkdir(parents=True)
        self.history = self.project / aider.HISTORY
        self.history.write_text(AIDER_HISTORY, encoding="utf-8")
        self.patch(aider, "_found", {"at": 0.0, "paths": []})

    def test_reads_the_latest_run_with_a_request(self):
        session = aider.read(self.history)
        self.assertEqual(session.cwd, str(self.project))
        self.assertEqual(session.model, "claude-sonnet-5")
        self.assertEqual(session.asks, ["add a --json flag to the cli\nand document it"])
        self.assertTrue(session.agent_last.startswith("I'll add the flag in cli.py."))
        self.assertEqual(session.files, {os.path.join(str(self.project), "cli.py"): "edited"})
        self.assertEqual(session.commands, ["pytest -q", "pytest -q"])
        self.assertEqual(session.context_tokens, 13500)
        self.assertTrue(session.limit_hit)
        self.assertTrue(session.started.startswith("2026-09-29T09:00:00"))

    def test_finds_history_files_in_code_folders(self):
        with mock.patch.dict(os.environ, {"HANDOFF_SCAN": str(self.folder)}):
            self.assertEqual([ref for ref, _ in aider.discover()], [str(self.history)])
        self.assertEqual(aider.folder(self.history), str(self.project))
        self.assertEqual(sources.detect_tool(self.history), "aider")


@unittest.skipUnless(subprocess.run(["git", "--version"], capture_output=True).returncode == 0, "needs git")
class CommittedFilesTest(TempFolder):
    def git(self, *args, date=None):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t")
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        subprocess.run(["git", *args], cwd=self.folder, env=env, check=True, capture_output=True)

    def test_files_from_commits_made_during_the_session(self):
        self.git("init", "-q")
        (self.folder / "old.txt").write_text("old")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "before", date="2020-01-01T00:00:00Z")
        (self.folder / "new.py").write_text("x = 1")
        (self.folder / "old.txt").write_text("changed")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "during the session")
        session = Session(tool="Codex", path="log", started=time.strftime("%Y-%m-%dT%H:%M:%S.000Z",
                                                                          time.gmtime(time.time() - 3600)))
        root = self.folder.resolve()
        files = render.committed_files(root, render.git_since(session))
        self.assertEqual(files, {os.path.join(str(root), "new.py"): "added",
                                 os.path.join(str(root), "old.txt"): "edited"})
        section = render.build_section(session, root)
        self.assertIn("- `new.py` - added", section)
        self.assertIn("Commits made during this session:", section)
        self.assertNotIn("before", section.split("Commits made during this session:")[1])


class LauncherTest(TempFolder):
    def test_install_and_remove(self):
        target = self.folder / "bin" / ("handoff.cmd" if os.name == "nt" else "handoff")
        with mock.patch.object(system, "launcher_path", lambda: target), \
                mock.patch.object(system.shutil, "which", lambda name: None):
            path, _, note = system.install_launcher()
            self.assertEqual((path, note), (target, "installed"))
            self.assertIn(str(system.PACKAGE_PARENT), target.read_text(encoding="utf-8"))
            if os.name != "nt":
                result = subprocess.run([str(target), "--version"], capture_output=True, text=True)
                self.assertIn("handoff", result.stdout)
            self.assertEqual(system.remove_launcher(), target)
            self.assertFalse(target.exists())

    def test_never_overwrites_another_program(self):
        target = self.folder / "handoff"
        target.write_text("#!/bin/sh\necho someone else\n", encoding="utf-8")
        with mock.patch.object(system, "launcher_path", lambda: target), \
                mock.patch.object(system.shutil, "which", lambda name: None):
            self.assertIn("left alone", system.install_launcher()[2])
            self.assertIsNone(system.remove_launcher())
        self.assertIn("someone else", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
