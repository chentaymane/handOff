# Changelog

All notable changes to handoff. Versions follow [Semantic Versioning](https://semver.org).

## [2.1.0] - 2026-10-15

### Added
- One-command install for every CLI on the computer: `install.sh` (macOS, Linux) and `install.ps1` (Windows PowerShell), downloaded straight from GitHub. Run again to update.
- Install from inside more CLIs: GitHub Copilot CLI (`copilot plugin install chentaymane/handOff`) and Codex (`$skill-installer`).
- Codex skill metadata (`agents/openai.yaml`) with the handoff icon.
- MIT license, also shipped inside the skill folder (`LICENSE.txt`) so every installed copy carries it.
- Continuous integration on Linux, macOS and Windows, Python 3.8 to 3.13, including both installers.

### Changed
- The installer ends with a short summary: how to call the skill, how to update and how to remove it.
- README rewritten for people installing the skill; developer notes moved to `CONTRIBUTING.md`.

## [2.0.0] - 2026-10-15

### Added
- handoff is an Agent Skill: `skills/handoff/` holds `SKILL.md`, a per-CLI reference and the whole engine, so copying the folder is a complete install.
- `install.py` and `handoff skill install | uninstall | status | zip`: copies the skill into Claude Code, the shared `~/.agents/skills` folder (Codex, Cursor, Gemini CLI, Copilot CLI, OpenCode), Qwen Code, Windsurf, Antigravity, Goose, Amp and more.
- `now --tool AGENT`, `now --repo-only` and `sessions`, to write a handoff from your own session or recover another CLI's session that ended.
- Claude Code plugin marketplace (`.claude-plugin/`).

### Changed
- The engine moved from `handoff/` to `skills/handoff/scripts/handoff/`. The background watcher is now an optional extra that the skill offers.

## [1.1.0] - 2026-09-29

### Added
- Local web dashboard (`handoff dashboard`).
- Session readers for Qwen Code, GitHub Copilot CLI, Freebuff/Codebuff and Aider.
- `handoff install` and `handoff uninstall`.
- Files changed through commits are listed, not only files the agent edited.

## [1.0.0] - 2026-09-16

### Added
- The background watcher: reads Claude Code, Codex, Cursor, OpenCode and Gemini CLI session logs and keeps each project's `HANDOFF.md` current, with desktop alerts on usage limits.
- Before that, the first version of the skill: write, resume and recover `HANDOFF.md`.

[2.1.0]: https://github.com/chentaymane/handOff/compare/eacad9b...v2.1.0
[2.0.0]: https://github.com/chentaymane/handOff/commit/eacad9b
[1.1.0]: https://github.com/chentaymane/handOff/commit/0819762
[1.0.0]: https://github.com/chentaymane/handOff/commit/cd801a2
