import tempfile
import unittest
from pathlib import Path

from handoff import render
from handoff.sources import Session


def sample(root):
    session = Session(tool="Codex", path=Path(root) / "rollout.jsonl", cwd=str(root), model="gpt-5.5",
                      started="2026-09-16T10:00:00.000Z", updated="2026-09-16T11:00:00.000Z")
    session.asks = ["Make the uploader resumable", "and show progress"]
    session.agent_last = "Progress is saved.\n\nResume logic is next."
    session.plan = [("Save progress", "completed"), ("Resume on restart", "in_progress"), ("Progress bar", "pending")]
    session.plan_note = "Halfway there"
    session.files = {str(Path(root) / "src" / "upload.js"): "edited"}
    session.commands = ["npm test"]
    session.errors = ["fatal: not a git repository"]
    session.context_tokens, session.context_window = 103000, 258400
    session.limit_percent, session.limit_window, session.limit_resets = 87.0, "30-day", 1783174158
    session.tool_calls = 12
    return session


class TempFolder(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)


class RedactTest(unittest.TestCase):
    def test_masks_common_secrets(self):
        text = ("key sk-ant-api03-abcdefghijklmnop1234 and ghp_ABCDEFGHIJKLMNOPQRSTUVWX12 "
                "clone https://me:hunter22@github.com/x.git with password=hunter2hunter2")
        clean = render.redact(text)
        for secret in ("sk-ant-api03-abcdefghijklmnop1234", "ghp_ABCDEFGHIJKLMNOPQRSTUVWX12",
                       "hunter22", "hunter2hunter2"):
            self.assertNotIn(secret, clean)
        self.assertIn("https://github.com/x.git", clean)
        self.assertIn("password=[redacted]", clean)


class SectionTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.section = render.build_section(sample(self.root), self.root)

    def test_plan_and_next_steps(self):
        self.assertIn("- [x] Save progress", self.section)
        self.assertIn("- [ ] **Resume on restart** _(in progress)_", self.section)
        self.assertIn("1. Resume on restart\n2. Progress bar", self.section)

    def test_agents_own_files_are_not_listed(self):
        session = sample(self.root)
        memory = str(Path.home() / ".claude" / "projects" / "x" / "memory" / "note.md")
        session.files[memory] = "written"
        section = render.build_section(session, self.root)
        self.assertNotIn("note.md", section)
        self.assertIn("`src/upload.js` - edited", section)

    def test_goal_reply_and_session_facts(self):
        self.assertIn("> Make the uploader resumable", self.section)
        self.assertIn("**Latest request:**", self.section)
        self.assertIn("> Resume logic is next.", self.section)
        self.assertIn("`src/upload.js` - edited", self.section)
        self.assertIn("87% used of the 30-day window", self.section)
        self.assertIn("~103K of 258K tokens (40%)", self.section)
        self.assertIn("**Heads-up:** 87% of the usage limit is used.", self.section)
        self.assertTrue(self.section.startswith(render.START) and self.section.endswith(render.END))


class WriteTest(TempFolder):
    def setUp(self):
        super().setUp()
        self.session = sample(self.root)
        self.path = self.root / render.HANDOFF_NAME

    def section(self):
        return render.build_section(self.session, self.root)

    def test_creates_file_with_header(self):
        self.assertTrue(render.write_handoff(self.root, self.section()))
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(f"# HANDOFF: {self.root.name}"))
        self.assertIn(render.START, text)

    def test_keeps_notes_outside_its_section(self):
        self.path.write_text("# My notes\n\nKeep this.\n", encoding="utf-8")
        render.write_handoff(self.root, self.section())
        self.path.write_text(self.path.read_text(encoding="utf-8") + "\nAnd this footer.\n", encoding="utf-8")
        self.session.agent_last = "Something new."
        self.assertTrue(render.write_handoff(self.root, self.section()))
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("Keep this.", text)
        self.assertIn("And this footer.", text)
        self.assertIn("> Something new.", text)
        self.assertEqual(text.count(render.START), 1)

    def test_notes_that_mention_the_markers_stay_intact(self):
        notes = f"# Notes\n\nThe app owns the part between `{render.START}` and `{render.END}`.\n\nMore notes.\n"
        self.path.write_text(notes, encoding="utf-8")
        for reply in ("First.", "Second."):
            self.session.agent_last = reply
            render.write_handoff(self.root, self.section())
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(notes.rstrip("\n")))
        self.assertEqual(text.count("## Auto handoff"), 1)
        self.assertIn("> Second.", text)
        self.assertNotIn("> First.", text)

    def test_timestamp_alone_does_not_rewrite(self):
        render.write_handoff(self.root, self.section())
        self.assertFalse(render.write_handoff(self.root, render.STAMP.sub("_Last update: later_", self.section())))

    def test_keeps_windows_line_endings(self):
        self.path.write_bytes(b"# Notes\r\n\r\nline\r\n")
        render.write_handoff(self.root, self.section())
        data = self.path.read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))


class HelpersTest(unittest.TestCase):
    def test_context_window_is_assumed_when_unknown(self):
        session = Session(tool="Claude Code", path=Path("x"), context_tokens=150000)
        self.assertEqual(render.context_percent(session), (75, 200000))
        session.context_tokens = 300000
        self.assertEqual(render.context_percent(session), (30, 1000000))

    def test_quote_trims_and_collapses_blank_lines(self):
        self.assertEqual(render.quote("a\n\n\n\nb", 100), "> a\n>\n> b")
        self.assertTrue(render.quote("x" * 50, 10).endswith(" ..."))


if __name__ == "__main__":
    unittest.main()
