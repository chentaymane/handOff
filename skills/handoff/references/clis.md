# The handoff skill in each coding CLI

`scripts/handoff.py skill install` copies the skill into the user-level skills folder of every CLI it finds. This table is what it uses, plus where each CLI keeps the session logs the script reads.

| CLI | Skills folder it reads (user level) | Call the skill | Session logs the script reads | `--tool` |
|---|---|---|---|---|
| Claude Code | `~/.claude/skills/` | `/handoff` | `~/.claude/projects` | `claude` |
| Codex | `~/.agents/skills/` | `$handoff`, or `/skills` | `~/.codex/sessions` (or `$CODEX_HOME`) | `codex` |
| Cursor | `~/.cursor/skills/`, `~/.agents/skills/`, `~/.claude/skills/` | `/handoff` | `~/.cursor` transcripts and `state.vscdb` | `cursor` |
| Gemini CLI | `~/.gemini/skills/`, `~/.agents/skills/` | ask for it; `/skills list` | `~/.gemini/tmp/*/chats` | `gemini` |
| GitHub Copilot CLI | `~/.copilot/skills/`, `~/.agents/skills/` | `/handoff`, or ask for it | `~/.copilot/session-state` | `copilot` |
| OpenCode | `~/.config/opencode/skills/`, `~/.agents/skills/`, `~/.claude/skills/` | ask for it | `~/.local/share/opencode/opencode.db` | `opencode` |
| Qwen Code | `~/.qwen/skills/` | `/handoff` | `~/.qwen/tmp/*/chats` | `qwen` |
| Windsurf | `~/.codeium/windsurf/skills/` | ask for it | not read: use `--repo-only` | |
| Antigravity | `~/.gemini/antigravity/skills/` | ask for it | not read (binary format): `--repo-only` | |
| Amp | `~/.config/agents/skills/` | ask for it | not read: `--repo-only` | |
| Goose | `~/.config/goose/skills/` | ask for it | not read: `--repo-only` | |
| Factory Droid | `~/.factory/skills/` | ask for it | not read: `--repo-only` | |
| Kiro CLI | `~/.kiro/skills/` | ask for it | not read: `--repo-only` | |
| Crush, Kilo Code, Roo Code, Augment, Trae, Continue, Junie, OpenHands | `~/.config/crush/skills/`, `~/.kilo/skills/`, `~/.roo/skills/`, `~/.augment/skills/`, `~/.trae/skills/`, `~/.continue/skills/`, `~/.junie/skills/`, `~/.openhands/skills/` | ask for it | not read: `--repo-only` | |
| Freebuff / Codebuff | no skills folder | say "Read ~/.agents/skills/handoff/SKILL.md and follow it" | `~/.config/manicode/projects` (or `$FREEBUFF_CONFIG_DIR`) | `codebuff` |
| Aider | no skills folder | `aider --read ~/.agents/skills/handoff/SKILL.md` | `.aider.chat.history.md` in the project | `aider` |

Codex, Cursor, Gemini CLI, Copilot CLI and OpenCode all read the shared `~/.agents/skills/` folder of the Agent Skills standard, so one copy there serves all five. Cursor and OpenCode also read `~/.claude/skills/`, so they may list the skill twice; both copies are the same.

## Project level

To give everyone who clones a repository the skill, copy the `handoff` folder into the repository's `.agents/skills/` (Codex, Cursor, Gemini CLI, Copilot CLI, OpenCode) and `.claude/skills/` (Claude Code), and commit it.

## Other ways to install

- **Any CLI, from GitHub:** `npx skills add chentaymane/handoff` (the open-source `skills` installer; `-a claude-code -a codex` picks agents, `-g` installs for the user instead of the project).
- **Claude Code plugin:** `/plugin marketplace add chentaymane/handoff`, then `/plugin install handoff@handoff`. As a plugin, the skill is called `/handoff:handoff`.
- **Gemini CLI:** `gemini skills install https://github.com/chentaymane/handoff --path skills/handoff`.
- **Upload as a zip** (claude.ai and skill marketplaces): `scripts/handoff.py skill zip` writes `handoff-skill.zip`. Uploaded skills run in a sandbox without your session logs, so there the writing and resuming parts work and the log-reading commands find nothing.

## Environment variables

| Variable | What it does |
|---|---|
| `HANDOFF_HOME` | Where the watcher keeps its own files (default `~/.handoff`) |
| `HANDOFF_SCAN` | Folders to search for Aider projects, separated like `PATH` |
| `CODEX_HOME` | Codex's data folder, if moved |
| `FREEBUFF_CONFIG_DIR` | Freebuff's data folder, if moved |
