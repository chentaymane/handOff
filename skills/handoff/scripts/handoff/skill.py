"""Copy this skill into the skills folder of every coding CLI on the computer, or package it for upload."""

import os
import re
import shutil
import zipfile
from pathlib import Path

from . import system

NAME = "handoff"
SKILL_DIR = system.PACKAGE_PARENT.parent  # <skill>/scripts/handoff/ -> <skill>/, the folder with SKILL.md
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_SUFFIXES = (".pyc", ".pyo", ".tmp")

# (key, who reads it, skills folder under home, folders under home that show the CLI is installed).
# None means always: ~/.agents/skills is the shared folder of the Agent Skills standard.
TARGETS = [
    ("claude", "Claude Code", ".claude/skills", (".claude",)),
    ("agents", "Codex, Cursor, Gemini CLI, Copilot CLI, OpenCode", ".agents/skills", None),
    ("qwen", "Qwen Code", ".qwen/skills", (".qwen",)),
    ("windsurf", "Windsurf", ".codeium/windsurf/skills", (".codeium/windsurf",)),
    ("antigravity", "Antigravity", ".gemini/antigravity/skills", (".gemini/antigravity",)),
    ("amp", "Amp", ".config/agents/skills", (".config/amp", ".config/agents")),
    ("goose", "Goose", ".config/goose/skills", (".config/goose",)),
    ("droid", "Factory Droid", ".factory/skills", (".factory",)),
    ("kiro", "Kiro CLI", ".kiro/skills", (".kiro",)),
    ("crush", "Crush", ".config/crush/skills", (".config/crush",)),
    ("kilo", "Kilo Code", ".kilo/skills", (".kilo",)),
    ("roo", "Roo Code", ".roo/skills", (".roo",)),
    ("augment", "Augment", ".augment/skills", (".augment",)),
    ("trae", "Trae", ".trae/skills", (".trae",)),
    ("continue", "Continue", ".continue/skills", (".continue",)),
    ("junie", "Junie", ".junie/skills", (".junie",)),
    ("openhands", "OpenHands", ".openhands/skills", (".openhands",)),
]
KEYS = [key for key, *_ in TARGETS]
ABSENT = "skipped: not on this computer"


def targets(only=None):
    """Every place the skill can go, as dicts: key, label, folder (where the skill goes), found (CLI installed)."""
    home = Path.home()
    found = []
    for key, label, skills, markers in TARGETS:
        if only and key not in only:
            continue
        found.append({"key": key, "label": label, "folder": home / skills / NAME,
                      "found": markers is None or any((home / marker).is_dir() for marker in markers)})
    return found


def parse_only(text):
    """'claude, qwen' -> ['claude', 'qwen']; raises ValueError naming the unknown ones."""
    if not text:
        return None
    keys = [item.strip().lower() for item in str(text).split(",") if item.strip()]
    unknown = [key for key in keys if key not in KEYS]
    if unknown:
        raise ValueError(f"unknown: {', '.join(unknown)} (choose from {', '.join(KEYS)})")
    return keys


def frontmatter(folder):
    """{'name': ..., 'version': ...} from a skill's SKILL.md, or {} when there is none."""
    try:
        text = (Path(folder) / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    match = re.match(r"---[ \t]*\r?\n(.*?)\r?\n---", text, re.S)
    if not match:
        return {}
    head = match.group(1)
    name = re.search(r"^name:[ \t]*['\"]?([^'\"\s]+)", head, re.M)
    version = re.search(r"^[ \t]+version:[ \t]*['\"]?([^'\"\s]+)", head, re.M)
    return {"name": name.group(1) if name else "", "version": version.group(1) if version else ""}


def source_ok():
    return (SKILL_DIR / "SKILL.md").is_file() and frontmatter(SKILL_DIR).get("name") == NAME


def _same(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _files(folder):
    """Relative paths of the files that make up the skill, without caches."""
    out = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for name in sorted(filenames):
            if not name.endswith(SKIP_SUFFIXES):
                out.append(os.path.relpath(os.path.join(dirpath, name), folder))
    return out


def copy_skill(source, destination):
    """Make `destination` an exact copy of the skill, in place.

    Files are overwritten one by one instead of swapping folders, because Windows refuses to rename
    a folder that a running watcher uses as its working directory.
    """
    source, destination = Path(source), Path(destination)
    wanted = set(_files(source))
    for relative in sorted(wanted):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    for relative in _files(destination) if destination.is_dir() else []:
        if relative not in wanted:
            try:
                (destination / relative).unlink()
            except OSError:
                pass
    for dirpath, dirnames, filenames in sorted(os.walk(destination), key=lambda item: -len(item[0])):
        if not os.listdir(dirpath) and Path(dirpath) != destination:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass


def install(only=None, dry_run=False):
    """Copy the skill into each CLI found (or each one in `only`). Returns [(target, note)]."""
    version = frontmatter(SKILL_DIR).get("version", "")
    results = []
    for target in targets(only):
        folder = target["folder"]
        if not target["found"] and not only:
            results.append((target, ABSENT))
            continue
        if _same(folder, SKILL_DIR):
            results.append((target, "this copy"))
            continue
        old = frontmatter(folder) if folder.exists() else None
        if old is not None and old.get("name") != NAME:
            results.append((target, "skipped: a different skill is already in that folder"))
            continue
        if old is None:
            note = "installed"
        elif old.get("version") == version:
            note = "reinstalled"
        else:
            note = f"updated from {old.get('version') or 'an older version'}"
        if not dry_run:
            try:
                copy_skill(SKILL_DIR, folder)
            except OSError as error:
                note = f"failed: {error}"
        results.append((target, ("would be " + note) if dry_run else note))
    return results


def _watcher_runs_from(folder):
    """Whether the `handoff` command or the login item points into this copy of the skill."""
    needle = os.path.normcase(str(Path(folder) / "scripts"))
    for path in (system.launcher_path(), system.autostart_path()):
        try:
            if needle in os.path.normcase(path.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def uninstall(only=None):
    """Remove the skill from each CLI's skills folder. Returns [(target, note)]."""
    results = []
    for target in targets(only):
        folder = target["folder"]
        if not folder.exists():
            continue
        if frontmatter(folder).get("name") != NAME:
            results.append((target, "left alone: a different skill is in that folder"))
            continue
        note = "removed"
        if _watcher_runs_from(folder):
            system.stop_background()
            system.set_autostart(False)
            system.remove_launcher()
            note = "removed, and stopped the watcher that ran from it"
        shutil.rmtree(folder, ignore_errors=True)
        if folder.exists():
            note = "partly removed: some files are in use, delete the folder by hand"
        results.append((target, note))
    return results


def status():
    """[(target, installed version or None)] for every place the skill can go."""
    out = []
    for target in targets():
        info = frontmatter(target["folder"]) if target["folder"].exists() else {}
        out.append((target, (info.get("version") or "older version") if info.get("name") == NAME else None))
    return out


def make_zip(path):
    """Package the skill as a zip with a top-level `handoff/` folder, the layout skill uploads expect."""
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    files = [relative for relative in _files(SKILL_DIR) if not _same(SKILL_DIR / relative, path)]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            archive.write(SKILL_DIR / relative, f"{NAME}/{Path(relative).as_posix()}")
    return path
