# Contributing to handoff

Thanks for helping. Bug reports, misread session logs and new CLIs are all welcome: [open an issue](https://github.com/chentaymane/handOff/issues) or a pull request.

## Layout

```
skills/handoff/                  the skill: everything an installed copy contains
  SKILL.md                       the instructions agents follow
  references/clis.md             each CLI's folders and how to call the skill there
  agents/openai.yaml             Codex display metadata
  assets/icon.svg
  LICENSE.txt
  scripts/handoff.py             what agents run
  scripts/handoff/               the engine (standard library only)
    cli.py                       every command
    skill.py                     the cross-CLI installer and the zip
    sources/                     one reader per CLI's session logs
    render.py                    the auto section of HANDOFF.md, git facts, secret masking
    watch.py, system.py          the optional background watcher
    app.py, dashboard.py         shared logic and the local dashboard
install.py                       local installer (python3 install.py)
install.sh, install.ps1          one-command installers that download from GitHub
.claude-plugin/                  Claude Code and Copilot CLI plugin manifests
tests/
```

## Run the tests

You need Python 3.8 or newer and nothing else.

```bash
python3 -m unittest discover -s tests -t .
python3 install.py --dry-run
```

Tests never touch your real CLI folders: the installer tests use a temporary home folder, and reader tests redirect every path they scan.

## Add a CLI whose session logs handoff reads

Add a module in `skills/handoff/scripts/handoff/sources/` with three functions:

```python
NAME = "mycli"           # what `--tool` accepts
LABEL = "My CLI"         # what people see

def discover(max_age_hours):  # yield (ref, stamp) for each session; stamp changes whenever the session does
def read(ref):                # return a Session: requests, replies, plan, files, commands, errors, tokens, limits
def folder(ref):              # the session's project folder, found cheaply
```

Register it in `MODULES` in `sources/__init__.py`, add a test with a small sample log, and it shows up in `now`, `sessions`, `status`, the watcher and the dashboard.

## Add a CLI the installer copies the skill into

Add a line to `TARGETS` in `skills/handoff/scripts/handoff/skill.py`: a key, who reads the folder, the skills folder under home, and the folders that show the CLI is installed. Add a row to `references/clis.md` and to the README table.

## Release a new version

1. Set the version in all four places (the tests fail if they differ): `metadata.version` in `skills/handoff/SKILL.md`, `skills/handoff/scripts/handoff/__init__.py`, `.claude-plugin/plugin.json` and `pyproject.toml`.
2. Add the changes to `CHANGELOG.md`.
3. Run the tests and `claude plugin validate .`.
4. Commit, tag `vX.Y.Z`, push, and create a GitHub release with `python3 install.py zip` attached.

## Style

Plain, short sentences in docs and messages. Standard library only. Never write outside the marker lines of a `HANDOFF.md`, and never change an agent's own data.
