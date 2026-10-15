import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from handoff import __version__, app, render, skill, sources

ROOT = Path(__file__).resolve().parent.parent


class SkillFolderTest(unittest.TestCase):
    """The skill must follow the Agent Skills format that every CLI reads."""

    def setUp(self):
        self.text = (skill.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    def test_name_matches_folder_and_version_matches_engine(self):
        self.assertEqual(skill.SKILL_DIR.name, "handoff")
        self.assertEqual(skill.frontmatter(skill.SKILL_DIR), {"name": "handoff", "version": __version__})

    def test_frontmatter_fits_the_limits(self):
        head = re.match(r"---\n(.*?)\n---\n", self.text, re.S).group(1)
        description = re.search(r"^description: (.+)$", head, re.M).group(1)
        compatibility = re.search(r"^compatibility: (.+)$", head, re.M).group(1)
        self.assertLessEqual(len(description), 1024)
        self.assertLessEqual(len(compatibility), 500)
        self.assertNotIn("<", description)  # some CLIs reject angle brackets in the description
        self.assertLess(self.text.count("\n"), 500)

    def test_commands_it_documents_exist(self):
        for command in ("now --tool", "now --repo-only", "sessions", "now --from", "skill install", "status"):
            self.assertIn(f"`{command}", self.text)
        self.assertTrue((skill.SKILL_DIR / "scripts" / "handoff.py").is_file())
        self.assertTrue((skill.SKILL_DIR / "references" / "clis.md").is_file())

    def test_plugin_manifests_agree(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], __version__)
        self.assertEqual(market["plugins"][0]["name"], plugin["name"])
        self.assertIn(f'version = "{__version__}"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_release_files_agree(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"badge/version-{__version__}-", readme)
        self.assertIn(f"## [{__version__}]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertEqual((ROOT / "LICENSE").read_text(encoding="utf-8"),
                         (skill.SKILL_DIR / "LICENSE.txt").read_text(encoding="utf-8"))

    def test_codex_metadata_points_at_real_files(self):
        meta = (skill.SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        for path in re.findall(r'icon_\w+:\s*"\./([^"]+)"', meta):
            self.assertTrue((skill.SKILL_DIR / path).is_file(), path)

    def test_shell_installer_keeps_unix_line_endings(self):
        self.assertIn("*.sh text eol=lf", (ROOT / ".gitattributes").read_text(encoding="utf-8"))
        script = (ROOT / "install.sh").read_bytes()
        self.assertTrue(script.startswith(b"#!/bin/sh\n"))
        for installer in ("install.sh", "install.ps1"):
            self.assertIn("raw.githubusercontent.com/chentaymane/handOff/main/" + installer,
                          (ROOT / installer).read_text(encoding="utf-8"))


class InstallTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        patcher = mock.patch("pathlib.Path.home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def notes(self, results):
        return {target["key"]: note for target, note in results}

    def test_installs_into_found_clis_and_the_shared_folder(self):
        (self.home / ".claude").mkdir()
        notes = self.notes(skill.install())
        self.assertEqual(notes["claude"], "installed")
        self.assertEqual(notes["agents"], "installed")  # always: Codex, Cursor, Gemini CLI, Copilot, OpenCode
        self.assertEqual(notes["qwen"], skill.ABSENT)
        for folder in (".claude/skills/handoff", ".agents/skills/handoff"):
            self.assertEqual(skill.frontmatter(self.home / folder)["version"], __version__)
            self.assertTrue((self.home / folder / "scripts" / "handoff" / "cli.py").is_file())
            self.assertFalse(list((self.home / folder).rglob("__pycache__")))
        self.assertFalse((self.home / ".qwen").exists())

    def test_updates_an_old_copy_and_removes_its_stale_files(self):
        old = self.home / ".claude" / "skills" / "handoff"
        (old / "scripts").mkdir(parents=True)
        (old / "SKILL.md").write_text("---\nname: handoff\ndescription: old\n---\n", encoding="utf-8")
        (old / "scripts" / "snapshot.py").write_text("print('old')\n", encoding="utf-8")
        self.assertEqual(self.notes(skill.install(["claude"]))["claude"], "updated from an older version")
        self.assertFalse((old / "scripts" / "snapshot.py").exists())
        self.assertEqual(self.notes(skill.install(["claude"]))["claude"], "reinstalled")

    def test_never_overwrites_a_different_skill(self):
        other = self.home / ".qwen" / "skills" / "handoff"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("---\nname: something-else\ndescription: x\n---\n", encoding="utf-8")
        self.assertIn("different skill", self.notes(skill.install())["qwen"])
        self.assertIn("different skill", self.notes(skill.uninstall())["qwen"])
        self.assertIn("something-else", (other / "SKILL.md").read_text(encoding="utf-8"))

    def test_dry_run_changes_nothing(self):
        self.assertEqual(self.notes(skill.install(dry_run=True))["agents"], "would be installed")
        self.assertFalse((self.home / ".agents").exists())

    def test_uninstall_removes_only_its_own_folders(self):
        (self.home / ".claude").mkdir()
        skill.install()
        (self.home / ".claude" / "skills" / "keep-me").mkdir()
        self.assertEqual(set(self.notes(skill.uninstall()).values()), {"removed"})
        self.assertFalse((self.home / ".agents" / "skills" / "handoff").exists())
        self.assertTrue((self.home / ".claude" / "skills" / "keep-me").exists())

    def test_only_rejects_unknown_names(self):
        self.assertEqual(skill.parse_only("claude, qwen"), ["claude", "qwen"])
        with self.assertRaises(ValueError):
            skill.parse_only("claude,nope")

    def test_zip_has_the_upload_layout(self):
        path = skill.make_zip(self.home / "out" / "handoff-skill.zip")
        names = zipfile.ZipFile(path).namelist()
        self.assertIn("handoff/SKILL.md", names)
        self.assertIn("handoff/scripts/handoff/cli.py", names)
        self.assertFalse([name for name in names if "__pycache__" in name or not name.startswith("handoff/")])


class EngineTest(unittest.TestCase):
    def test_tool_names_people_use(self):
        for text, name in [("Claude Code", "claude"), ("gemini-cli", "gemini"), ("GitHub Copilot", "copilot"),
                           ("Copilot CLI", "copilot"), ("freebuff", "codebuff"), ("Qwen Code", "qwen"),
                           ("codex", "codex"), ("windsurf", None)]:
            self.assertEqual(sources.tool_name(text), name, text)

    def test_find_session_can_keep_to_one_agent(self):
        found = [("claude", "c.jsonl", 3), ("codex", "x.jsonl", 2)]
        with mock.patch.object(sources, "transcripts", lambda hours, only=None: [f for f in found if not only or f[0] == only]), \
                mock.patch.object(sources, "session_cwd", lambda tool, ref: str(ROOT)):
            self.assertEqual(app.find_session(ROOT), ("claude", "c.jsonl"))
            self.assertEqual(app.find_session(ROOT, tool="codex"), ("codex", "x.jsonl"))
            self.assertIsNone(app.find_session(ROOT, tool="gemini"))

    def test_repo_only_section(self):
        with tempfile.TemporaryDirectory() as folder:
            section = render.build_repo_section(Path(folder), "no Codex session found")
        self.assertTrue(section.startswith(render.START) and section.endswith(render.END))
        self.assertIn("Repo facts only (no Codex session found)", section)
        self.assertIn("### Repo", section)


if __name__ == "__main__":
    unittest.main()
