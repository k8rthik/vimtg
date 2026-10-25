"""How the CLI words an ordinary environment error."""

from __future__ import annotations

import errno
import sqlite3

from vimtg.config.paths import db_path


def friendly_error(exc: OSError | UnicodeDecodeError | sqlite3.Error) -> str:
    """A one-line message plus a hint for an ordinary environment error."""
    if isinstance(exc, UnicodeDecodeError):
        return (
            f"cannot read file: it is not UTF-8 text ({exc.reason}).\n"
            "Hint: re-save the deck as UTF-8, or check you passed the right file."
        )
    if isinstance(exc, sqlite3.Error):
        return (
            f"card database error: {exc}\n"
            f"Hint: the database at {db_path()} may be corrupt — run "
            "`vimtg sync` (or start vimtg) to rebuild it; deck history is "
            "salvaged and the damaged file kept as a backup."
        )
    target = exc.filename if exc.filename is not None else ""
    reason = exc.strerror or str(exc)
    hint = {
        errno.ENOENT: "check the path exists (and its parent directory, for output files).",
        errno.EISDIR: "pass a deck file, not a directory.",
        errno.ENOTDIR: "a component of the path is not a directory.",
        errno.EACCES: "check the file and directory permissions.",
        errno.EPERM: "check the file and directory permissions.",
        errno.ENOSPC: "free some disk space and retry.",
    }.get(exc.errno or 0)
    msg = f"{target}: {reason}" if target else reason
    return msg + (f"\nHint: {hint}" if hint else "")
