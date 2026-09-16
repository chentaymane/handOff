import json
import os
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from handoff import sources

WORK = r"C:\work\shop" if os.name == "nt" else "/work/shop"
T0 = "2026-09-16T10:00:00.000Z"


def jsonl(path, entries):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    return path


CLAUDE_LOG = [
    {"type": "permission-mode", "permissionMode": "default"},
    {"type": "user", "cwd": WORK, "timestamp": T0,
     "message": {"role": "user", "content": "Build a login page with email and password"}},
    {"type": "user", "isMeta": True, "cwd": WORK, "timestamp": T0,
     "message": {"role": "user", "content": [{"type": "text", "text": "Base directory for this skill: x"}]}},
    {"type": "assistant", "cwd": WORK, "timestamp": "2026-09-16T10:01:00.000Z",
     "message": {"model": "claude-opus-5",
                 "usage": {"input_tokens": 1000, "cache_read_input_tokens": 149000, "output_tokens": 500},
                 "content": [
                     {"type": "text", "text": "Starting with the form."},
                     {"type": "tool_use", "name": "Write", "input": {"file_path": WORK + "/login.html"}},
                     {"type": "tool_use", "name": "Edit", "input": {"file_path": WORK + "/login.html"}},
                     {"type": "tool_use", "name": "Bash", "input": {"command": "npm test"}},
                     {"type": "tool_use", "name": "TodoWrite", "input": {"todos": [
                         {"content": "Form", "status": "completed"},
                         {"content": "Validation", "status": "in_progress"},
                         {"content": "Tests", "status": "pending"}]}}]}},
    {"type": "user", "cwd": WORK, "timestamp": "2026-09-16T10:02:00.000Z",
     "message": {"role": "user", "content": [
         {"type": "tool_result", "is_error": True, "content": "npm ERR! missing script: test"}]}},
    {"type": "user", "cwd": WORK, "timestamp": "2026-09-16T10:03:00.000Z",
     "message": {"role": "user", "content": [
         {"type": "text", "text": "<system-reminder>internal</system-reminder>"},
         {"type": "text", "text": "Also add a remember-me checkbox"}]}},
    {"type": "assistant", "isSidechain": True, "timestamp": "2026-09-16T10:04:00.000Z",
     "message": {"usage": {"input_tokens": 999999}, "content": [{"type": "text", "text": "subagent chatter"}]}},
    {"type": "assistant", "isApiErrorMessage": True, "error": "rate_limit", "timestamp": "2026-09-16T10:05:00.000Z",
     "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "Usage credits are required"}]}},
]

CODEX_LOG = [
    {"timestamp": T0, "type": "session_meta", "payload": {"id": "abc", "cwd": WORK}},
    {"timestamp": T0, "type": "turn_context", "payload": {"cwd": WORK, "model": "gpt-5.5"}},
    {"timestamp": T0, "type": "event_msg", "payload": {"type": "task_started", "model_context_window": 258400}},
    {"timestamp": T0, "type": "event_msg", "payload": {"type": "user_message", "message": "Make the uploader resumable"}},
    {"timestamp": T0, "type": "response_item",
     "payload": {"type": "function_call", "name": "shell_command", "arguments": json.dumps({"command": "git status"})}},
    {"timestamp": T0, "type": "response_item",
     "payload": {"type": "function_call_output",
                 "output": "Exit code: 1\nWall time: 1 seconds\nOutput:\nfatal: not a git repository\n"}},
    {"timestamp": T0, "type": "response_item",
     "payload": {"type": "custom_tool_call", "name": "apply_patch",
                 "input": "*** Begin Patch\n*** Update File: src/upload.js\n*** End Patch\n"}},
    {"timestamp": T0, "type": "event_msg",
     "payload": {"type": "patch_apply_end", "changes": {WORK + "\\src\\upload.js": {"type": "update"}}}},
    {"timestamp": T0, "type": "response_item",
     "payload": {"type": "function_call", "name": "update_plan", "arguments": json.dumps({
         "plan": [{"step": "Save progress to disk", "status": "completed"},
                  {"step": "Resume on restart", "status": "in_progress"}],
         "explanation": "Halfway there"})}},
    {"timestamp": T0, "type": "event_msg",
     "payload": {"type": "agent_message", "message": "Progress is saved; resume logic is next."}},
    {"timestamp": "2026-09-16T10:30:00.000Z", "type": "event_msg",
     "payload": {"type": "token_count",
                 "info": {"last_token_usage": {"input_tokens": 100000, "output_tokens": 3000},
                          "model_context_window": 258400},
                 "rate_limits": {"primary": {"used_percent": 87.0, "window_minutes": 43200, "resets_at": 1783174158},
                                 "secondary": {"used_percent": 20.0, "window_minutes": 300},
                                 "rate_limit_reached_type": None}}},
]


class TempFolder(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)


class ClaudeTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.session = sources.read_claude(jsonl(self.folder / "one.jsonl", CLAUDE_LOG))

    def test_user_requests_skip_injected_and_system_text(self):
        self.assertEqual(self.session.asks, ["Build a login page with email and password",
                                             "Also add a remember-me checkbox"])

    def test_folder_model_and_times(self):
        self.assertEqual(self.session.cwd, WORK)
        self.assertEqual(self.session.model, "claude-opus-5")
        self.assertEqual((self.session.started, self.session.updated), (T0, "2026-09-16T10:05:00.000Z"))

    def test_files_commands_and_plan(self):
        self.assertEqual(self.session.files, {WORK + "/login.html": "written"})
        self.assertEqual(self.session.commands, ["npm test"])
        self.assertEqual(self.session.plan,
                         [("Form", "completed"), ("Validation", "in_progress"), ("Tests", "pending")])
        self.assertEqual(self.session.tool_calls, 4)

    def test_context_and_last_reply_ignore_subagents(self):
        self.assertEqual(self.session.context_tokens, 150500)
        self.assertEqual(self.session.agent_last, "Starting with the form.")

    def test_errors_and_usage_limit(self):
        self.assertTrue(self.session.limit_hit)
        self.assertTrue(any("npm ERR! missing script" in error for error in self.session.errors))
        self.assertTrue(any("rate_limit" in error for error in self.session.errors))

    def test_compaction_resets_context(self):
        path = jsonl(self.folder / "two.jsonl", CLAUDE_LOG + [{"type": "system", "subtype": "compact_boundary"}])
        self.assertEqual(sources.read_claude(path).context_tokens, 0)


class CodexTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.session = sources.read_codex(jsonl(self.folder / "rollout.jsonl", CODEX_LOG))

    def test_folder_model_request_and_reply(self):
        self.assertEqual((self.session.cwd, self.session.model), (WORK, "gpt-5.5"))
        self.assertEqual(self.session.asks, ["Make the uploader resumable"])
        self.assertEqual(self.session.agent_last, "Progress is saved; resume logic is next.")

    def test_ide_preamble_is_left_out_of_requests(self):
        ide = {"timestamp": T0, "type": "event_msg", "payload": {
            "type": "user_message",
            "message": "# Context from my IDE setup:\n\n## Open tabs:\n- a.js\n\n## My request for Codex:\nFix the upload bug"}}
        session = sources.read_codex(jsonl(self.folder / "ide.jsonl", CODEX_LOG + [ide]))
        self.assertEqual(session.asks[-1], "Fix the upload bug")

    def test_plan_with_explanation(self):
        self.assertEqual(self.session.plan,
                         [("Save progress to disk", "completed"), ("Resume on restart", "in_progress")])
        self.assertEqual(self.session.plan_note, "Halfway there")

    def test_files_come_from_applied_patches(self):
        self.assertEqual(self.session.files, {WORK + "\\src\\upload.js": "edited"})

    def test_files_fall_back_to_patch_text(self):
        log = [entry for entry in CODEX_LOG if entry["payload"].get("type") != "patch_apply_end"]
        self.assertEqual(sources.read_codex(jsonl(self.folder / "b.jsonl", log)).files, {"src/upload.js": "edited"})

    def test_commands_and_failures(self):
        self.assertEqual(self.session.commands, ["git status"])
        self.assertEqual(self.session.errors, ["fatal: not a git repository"])

    def test_context_and_usage_limit(self):
        session = self.session
        self.assertEqual((session.context_tokens, session.context_window), (103000, 258400))
        self.assertEqual((session.limit_percent, session.limit_window, session.limit_resets),
                         (87.0, "30-day", 1783174158))
        self.assertFalse(session.limit_hit)

    def test_limit_reached(self):
        reached = {"timestamp": T0, "type": "event_msg", "payload": {
            "type": "token_count", "info": None,
            "rate_limits": {"primary": {"used_percent": 100.0, "window_minutes": 300},
                            "rate_limit_reached_type": "primary"}}}
        session = sources.read_codex(jsonl(self.folder / "c.jsonl", CODEX_LOG + [reached]))
        self.assertTrue(session.limit_hit)
        self.assertEqual((session.limit_percent, session.limit_window), (100.0, "5-hour"))
        self.assertEqual(session.context_tokens, 103000)


class DiscoveryTest(TempFolder):
    def test_finds_both_tools_newest_first(self):
        claude_dir, codex_dir, day = self.folder / "claude", self.folder / "codex", date.today()
        old = jsonl(claude_dir / "C--work-shop" / "one.jsonl", CLAUDE_LOG)
        new = jsonl(codex_dir / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}" / "rollout-1.jsonl", CODEX_LOG)
        os.utime(old, (time.time() - 100, time.time() - 100))
        with mock.patch.object(sources, "CLAUDE_PROJECTS", claude_dir), \
                mock.patch.object(sources, "CODEX_SESSIONS", codex_dir):
            found = sources.transcripts(24)
        self.assertEqual([(tool, path) for tool, path, _ in found], [("codex", new), ("claude", old)])
        self.assertEqual(sources.session_cwd("claude", old), WORK)
        self.assertEqual(sources.session_cwd("codex", new), WORK)

    def test_window_labels(self):
        self.assertEqual([sources.window_label(minutes) for minutes in (300, 10080, 43200, 120, None)],
                         ["5-hour", "weekly", "30-day", "2-hour", ""])

    def test_missing_log_gives_none(self):
        self.assertIsNone(sources.read_session("codex", self.folder / "missing.jsonl"))


if __name__ == "__main__":
    unittest.main()
