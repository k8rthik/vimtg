"""Startup integrity check and recovery for the vimtg database.

The database file holds the card data (rebuildable from Scryfall with
a sync) and the user's deck history — the snapshots — which is NOT
rebuildable. A corrupt file must therefore never be thrown away:
recovery

1. copies the damaged file (and its WAL/SHM sidecars) byte for byte to
   ``<name>.corrupt-<timestamp>`` and leaves that copy alone,
2. builds a fresh database with an empty card table and copies every
   history row it can still read out of the damaged file into it,
3. swaps the fresh file into place.

A history table that cannot be read in full is copied up to the first
unreadable row and reported as partial; when nothing can be read the
report says so and the backup is the only copy of the history.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from vimtg.data.database import Database
from vimtg.data.schema import initialize_schema

# Tables holding user data. Card tables are not listed: a sync rebuilds
# them.
HISTORY_TABLES = ("snapshots",)

_SIDECARS = ("-wal", "-shm")
# Primary result codes that mean the file itself is damaged
_SQLITE_CORRUPT = 11
_SQLITE_NOTADB = 26


def is_corruption(exc: BaseException) -> bool:
    """True when a sqlite error means a damaged file — not a lock, a
    permission problem or a full disk, which recovery must not touch."""
    if not isinstance(exc, sqlite3.DatabaseError):
        return False
    code = getattr(exc, "sqlite_errorcode", None)
    if isinstance(code, int):
        return (code & 0xFF) in (_SQLITE_CORRUPT, _SQLITE_NOTADB)
    text = str(exc).lower()
    return "malformed" in text or "not a database" in text


def check_database(db: Database) -> None:
    """Integrity-check, then open and migrate `db`; raises sqlite3.Error.

    ``PRAGMA quick_check`` walks every page, so damage anywhere — card
    pages included — is found at startup instead of mid-edit. It runs
    before the schema migrations so a damaged file is never written to.
    """
    conn = db.connect()
    rows = conn.execute("PRAGMA quick_check(1)").fetchall()
    result = str(rows[0][0]) if rows else "ok"
    if result != "ok":
        raise sqlite3.DatabaseError(f"database disk image is malformed: {result}")
    db.initialize()


@dataclass(frozen=True)
class RecoveryReport:
    """What recovery saved. `salvaged` maps each history table to the
    rows copied; `complete` is False when any of it may be missing."""

    backup: Path
    salvaged: dict[str, int] = field(default_factory=dict)
    complete: bool = False
    error: str = ""

    def message(self, sync_hint: str = "run :sync to download it again") -> str:
        head = (
            "The card database was damaged and has been rebuilt without "
            f"card data — {sync_hint}."
        )
        snapshots = self.salvaged.get("snapshots", 0)
        if self.complete:
            history = f"Deck history was recovered ({snapshots} snapshots)."
        elif self.salvaged:
            history = (
                f"Deck history was only partly recovered ({snapshots} "
                "snapshots); some may be missing."
            )
        else:
            history = "Deck history could not be recovered."
        return f"{head} {history} The damaged file is kept at {self.backup}"


def _backup_path(path: Path, now: datetime) -> Path:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.corrupt-{stamp}")
    n = 1
    while candidate.exists():
        n += 1
        candidate = path.with_name(f"{path.name}.corrupt-{stamp}-{n}")
    return candidate


def _copy_with_sidecars(src: Path, dest: Path) -> None:
    shutil.copy2(src, dest)
    for suffix in _SIDECARS:
        side = src.with_name(src.name + suffix)
        if side.exists():
            shutil.copy2(side, dest.with_name(dest.name + suffix))


def _salvage_table(
    old: sqlite3.Connection, new: sqlite3.Connection, table: str
) -> tuple[int, bool]:
    """Copy `table` row by row; (rows copied, read in full)."""
    new_cols = [r[1] for r in new.execute(f"PRAGMA table_info({table})")]
    try:
        old_cols = {r[1] for r in old.execute(f"PRAGMA table_info({table})")}
    except sqlite3.DatabaseError:
        return 0, False
    if not old_cols:
        return 0, True  # the damaged file never had this table
    cols = [c for c in new_cols if c in old_cols]
    col_list = ", ".join(cols)
    insert = (
        f"INSERT OR IGNORE INTO {table} ({col_list}) "
        f"VALUES ({', '.join('?' for _ in cols)})"
    )
    copied = 0
    try:
        for row in old.execute(f"SELECT {col_list} FROM {table}"):
            new.execute(insert, tuple(row))
            copied += 1
    except sqlite3.DatabaseError:
        return copied, False
    return copied, True


def _salvage_history(source: Path, dest: Path) -> tuple[dict[str, int], bool, str]:
    """Build a fresh database at `dest` holding what `source`'s history
    tables still give up."""
    new = sqlite3.connect(str(dest))
    try:
        initialize_schema(new)
        salvaged: dict[str, int] = {}
        complete = True
        error = ""
        try:
            # Read-only: recovery never writes to the damaged copy
            old = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            return {}, False, str(exc)
        try:
            for table in HISTORY_TABLES:
                rows, full = _salvage_table(old, new, table)
                if rows:
                    salvaged[table] = rows
                complete = complete and full
        except sqlite3.Error as exc:
            complete, error = False, str(exc)
        finally:
            old.close()
        new.commit()
        if not complete and not salvaged and not error:
            error = "history tables are unreadable"
        return salvaged, complete, error
    finally:
        new.close()


def recover_database(path: Path, now: datetime | None = None) -> RecoveryReport:
    """Back up the damaged database at `path` and rebuild it in place,
    keeping every history row that can still be read.

    Raises OSError when the backup cannot be written — the damaged file
    is then left exactly as it was.
    """
    backup = _backup_path(path, now or datetime.now())
    _copy_with_sidecars(path, backup)
    rebuilt = path.with_name(path.name + ".rebuild")
    rebuilt.unlink(missing_ok=True)
    try:
        salvaged, complete, error = _salvage_history(backup, rebuilt)
        # The old WAL belongs to the damaged file; replayed into the
        # rebuilt one it would corrupt it again
        for suffix in _SIDECARS:
            path.with_name(path.name + suffix).unlink(missing_ok=True)
        os.replace(rebuilt, path)
    except BaseException:
        rebuilt.unlink(missing_ok=True)
        raise
    return RecoveryReport(backup, salvaged, complete, error)


@dataclass(frozen=True)
class OpenedDatabase:
    """A usable database plus anything the user must be told.

    `in_memory` marks the last-resort fallback: nothing is persisted.
    """

    db: Database
    warning: str = ""
    recovered: RecoveryReport | None = None
    in_memory: bool = False
    # Why the database could not be used, without the TUI's "running
    # without card data" consequence (a CLI command just stops)
    reason: str = ""


def open_database(
    path: Path,
    *,
    now: datetime | None = None,
    check: Callable[[Database], None] = check_database,
    sync_hint: str = "run :sync to download it again",
) -> OpenedDatabase:
    """Open the database at `path`, recovering it when it is damaged.

    Never raises for a damaged or unopenable file: as a last resort the
    session runs on an in-memory database (no card data, history not
    saved) and the warning says so.
    """
    db = Database(path)
    try:
        check(db)
        return OpenedDatabase(db)
    except sqlite3.Error as exc:
        db.close()
        if not is_corruption(exc):
            return _in_memory(f"Cannot open the card database {path}: {exc}.")
    try:
        report = recover_database(path, now)
    except OSError as exc:
        return _in_memory(
            f"The card database {path} is damaged and could not be backed "
            f"up ({exc}); it was left untouched."
        )
    db = Database(path)
    try:
        check(db)
    except sqlite3.Error as exc:
        db.close()
        return _in_memory(
            f"The card database {path} could not be rebuilt ({exc}); "
            f"the damaged file is kept at {report.backup}."
        )
    return OpenedDatabase(db, report.message(sync_hint), report)


def _in_memory(reason: str) -> OpenedDatabase:
    db = Database(Path(":memory:"))
    db.initialize()
    return OpenedDatabase(
        db,
        f"{reason} Running without card data; deck history is not "
        "saved this session.",
        in_memory=True,
        reason=reason,
    )
