"""Startup integrity check and recovery of a damaged database.

The database holds card data (rebuildable) and deck history (not), so
every test checks that the damaged bytes survive as a backup and that
readable history rows make it into the rebuilt file.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from vimtg.data.card_repository import CardRepository
from vimtg.data.database import Database
from vimtg.data.db_recovery import (
    check_database,
    is_corruption,
    open_database,
    recover_database,
)
from vimtg.domain.card import Card

NOW = datetime(2026, 10, 10, 12, 30, 0)
BACKUP_NAME = "cards.db.corrupt-20261010-123000"


@pytest.fixture
def opened() -> Iterator[list[Database]]:
    """Databases opened by a test, closed at teardown."""
    dbs: list[Database] = []
    yield dbs
    for db in dbs:
        db.close()


def _build(path: Path, real_shape_cards: list[dict[str, object]]) -> None:
    """A healthy database with cards and three history tables filled."""
    db = Database(path)
    db.initialize()
    CardRepository(db).replace_all(
        [Card.from_scryfall(d) for d in real_shape_cards],  # type: ignore[arg-type]
        synced_at="2026-10-01T00:00:00+00:00",
    )
    conn = db.connect()
    for i in range(3):
        conn.execute(
            "INSERT INTO snapshots (id, deck_path, parent_id, deck_state, timestamp, "
            "description, branch, deck_hash) VALUES (?, ?, ?, ?, ?, ?, 'main', '')",
            (f"s{i}", "/decks/burn.deck", f"s{i - 1}" if i else None,
             f"{i + 1} Lightning Bolt\n", f"2026-10-0{i + 1}T00:00:00", f"edit {i}"),
        )
    conn.execute(
        "INSERT INTO branches VALUES ('main', '/decks/burn.deck', 's2', '2026-10-01')"
    )
    conn.execute("INSERT INTO deck_heads VALUES ('/decks/burn.deck', 'main')")
    conn.commit()
    db.close()  # last connection: the WAL is checkpointed into the file


def _smash_table(path: Path, table: str) -> None:
    """Overwrite `table`'s root b-tree page with garbage."""
    conn = sqlite3.connect(path)
    root = conn.execute(
        "SELECT rootpage FROM sqlite_master WHERE name = ?", (table,)
    ).fetchone()[0]
    page_size = conn.execute("PRAGMA page_size").fetchone()[0]
    conn.close()
    with open(path, "r+b") as f:
        f.seek((root - 1) * page_size)
        f.write(b"\xab" * page_size)


def _rows(path: Path, sql: str) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


class TestIsCorruption:
    def test_malformed_and_notadb_are_corruption(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.db"
        bad.write_bytes(b"this is not sqlite" * 100)
        conn = sqlite3.connect(bad)
        with pytest.raises(sqlite3.DatabaseError) as info:
            conn.execute("SELECT * FROM sqlite_master").fetchall()
        conn.close()
        assert is_corruption(info.value)
        assert is_corruption(sqlite3.DatabaseError("database disk image is malformed"))

    def test_lock_is_not_corruption(self) -> None:
        assert not is_corruption(sqlite3.OperationalError("database is locked"))
        assert not is_corruption(OSError("disk full"))


class TestCheck:
    def test_healthy_database_passes(
        self, tmp_path: Path, real_shape_cards: list[dict[str, object]]
    ) -> None:
        path = tmp_path / "cards.db"
        _build(path, real_shape_cards)
        db = Database(path)
        try:
            check_database(db)
        finally:
            db.close()

    def test_damaged_card_pages_are_found_at_startup(
        self, tmp_path: Path, real_shape_cards: list[dict[str, object]]
    ) -> None:
        path = tmp_path / "cards.db"
        _build(path, real_shape_cards)
        _smash_table(path, "cards")
        db = Database(path)
        try:
            with pytest.raises(sqlite3.DatabaseError) as info:
                check_database(db)
        finally:
            db.close()
        assert is_corruption(info.value)


class TestRecover:
    def test_card_corruption_keeps_all_history(
        self, tmp_path: Path, real_shape_cards: list[dict[str, object]],
        opened: list[Database],
    ) -> None:
        path = tmp_path / "cards.db"
        _build(path, real_shape_cards)
        _smash_table(path, "cards")
        damaged = path.read_bytes()

        result = open_database(path, now=NOW)
        opened.append(result.db)

        report = result.recovered
        assert report is not None
        assert report.complete
        assert report.salvaged == {"snapshots": 3, "branches": 1, "deck_heads": 1}
        # The damaged bytes are kept untouched as the backup
        assert report.backup == tmp_path / BACKUP_NAME
        assert report.backup.read_bytes() == damaged
        # The live file is a working database: no cards, full history
        repo = CardRepository(result.db)
        assert repo.count() == 0
        assert repo.get_last_sync() is None  # next sync is due
        assert _rows(path, "SELECT id, deck_state FROM snapshots ORDER BY id") == [
            ("s0", "1 Lightning Bolt\n"),
            ("s1", "2 Lightning Bolt\n"),
            ("s2", "3 Lightning Bolt\n"),
        ]
        assert _rows(path, "SELECT * FROM deck_heads") == [("/decks/burn.deck", "main")]
        assert "Deck history was recovered (3 snapshots)" in result.warning
        assert str(report.backup) in result.warning
        assert ":sync" in result.warning

    def test_damaged_history_table_is_reported_partial(
        self, tmp_path: Path, real_shape_cards: list[dict[str, object]],
        opened: list[Database],
    ) -> None:
        path = tmp_path / "cards.db"
        _build(path, real_shape_cards)
        _smash_table(path, "snapshots")

        result = open_database(path, now=NOW)
        opened.append(result.db)

        report = result.recovered
        assert report is not None
        assert not report.complete
        # What could be read still made it across
        assert report.salvaged == {"branches": 1, "deck_heads": 1}
        assert "only partly recovered" in result.warning
        assert (tmp_path / BACKUP_NAME).exists()

    def test_unreadable_file_keeps_backup_and_says_so(
        self, tmp_path: Path, opened: list[Database]
    ) -> None:
        path = tmp_path / "cards.db"
        garbage = b"\x00garbage, not a database\xff" * 512
        path.write_bytes(garbage)

        result = open_database(path, now=NOW)
        opened.append(result.db)

        assert result.recovered is not None
        assert result.recovered.salvaged == {}
        assert not result.recovered.complete
        assert (tmp_path / BACKUP_NAME).read_bytes() == garbage
        assert "Deck history could not be recovered" in result.warning
        assert str(tmp_path / BACKUP_NAME) in result.warning
        # Editor stays usable: a fresh database that can store history
        assert not result.in_memory
        CardRepository(result.db).count()
        result.db.connect().execute("SELECT COUNT(*) FROM snapshots").fetchone()

    def test_stale_wal_is_backed_up_not_replayed(self, tmp_path: Path) -> None:
        path = tmp_path / "cards.db"
        path.write_bytes(b"junk" * 1024)
        wal = tmp_path / "cards.db-wal"
        wal.write_bytes(b"old wal")

        report = recover_database(path, NOW)

        assert not wal.exists()
        assert (tmp_path / f"{BACKUP_NAME}-wal").read_bytes() == b"old wal"
        assert report.backup.exists()

    def test_second_recovery_in_same_second_gets_its_own_backup(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "cards.db"
        path.write_bytes(b"junk" * 1024)
        first = recover_database(path, NOW).backup
        path.write_bytes(b"more junk" * 1024)
        second = recover_database(path, NOW).backup
        assert first != second
        assert first.read_bytes() == b"junk" * 1024
        assert second.read_bytes() == b"more junk" * 1024


class TestOpenFallbacks:
    def test_healthy_database_opens_without_warning(
        self, tmp_path: Path, real_shape_cards: list[dict[str, object]],
        opened: list[Database],
    ) -> None:
        path = tmp_path / "cards.db"
        _build(path, real_shape_cards)
        result = open_database(path, now=NOW)
        opened.append(result.db)
        assert result.warning == ""
        assert result.recovered is None
        assert CardRepository(result.db).count() == len(real_shape_cards)
        assert list(tmp_path.glob("*.corrupt-*")) == []

    def test_locked_database_is_never_recovered(
        self, tmp_path: Path, opened: list[Database]
    ) -> None:
        path = tmp_path / "cards.db"
        path.write_bytes(b"pretend this is fine")

        def locked(_db: Database) -> None:
            raise sqlite3.OperationalError("database is locked")

        result = open_database(path, now=NOW, check=locked)
        opened.append(result.db)
        assert result.in_memory
        assert "database is locked" in result.warning
        assert path.read_bytes() == b"pretend this is fine"
        assert list(tmp_path.glob("*.corrupt-*")) == []

    def test_backup_failure_leaves_file_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        opened: list[Database],
    ) -> None:
        from vimtg.data import db_recovery

        path = tmp_path / "cards.db"
        path.write_bytes(b"junk" * 1024)

        def no_space(*_a: object, **_k: object) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(db_recovery.shutil, "copy2", no_space)
        result = open_database(path, now=NOW)
        opened.append(result.db)
        assert result.in_memory
        assert "could not be backed up" in result.warning
        assert path.read_bytes() == b"junk" * 1024

    def test_rebuild_failure_falls_back_to_memory(
        self, tmp_path: Path, opened: list[Database]
    ) -> None:
        path = tmp_path / "cards.db"
        path.write_bytes(b"junk" * 1024)
        calls = [0]

        def always_corrupt(_db: Database) -> None:
            calls[0] += 1
            raise sqlite3.DatabaseError("database disk image is malformed")

        result = open_database(path, now=NOW, check=always_corrupt)
        opened.append(result.db)
        assert calls[0] == 2
        assert result.in_memory
        assert str(tmp_path / BACKUP_NAME) in result.warning
