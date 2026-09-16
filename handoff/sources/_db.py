"""Read-only access to the SQLite databases some agents keep their chats in."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote


def connect(path):
    """Open read-only, so the agent's own writes are never blocked or touched."""
    location = quote(Path(path).as_posix().lstrip("/"), safe="/:")
    return closing(sqlite3.connect(f"file:///{location}?mode=ro", uri=True, timeout=2))


def stamp(path):
    """A value that changes whenever the database does: the newest mtime of the file and its write-ahead log."""
    stamps = []
    for suffix in ("", "-wal"):
        try:
            stamps.append(os.stat(f"{path}{suffix}").st_mtime_ns)
        except OSError:
            pass
    return max(stamps) if stamps else None


def split_ref(ref):
    database, _, key = str(ref).rpartition("#")
    return database, key
