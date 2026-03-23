from pathlib import Path

from vimtg.data.database import Database


class TestDatabase:
    def test_database_creates_file(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.connect()
        assert tmp_db.exists()
        db.close()

    def test_database_wal_mode(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        conn = db.connect()
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"
        db.close()

    def test_schema_initialization(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.initialize()
        conn = db.connect()

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [row[0] for row in tables]

        assert "cards" in table_names
        assert "cards_fts" in table_names
        assert "sync_metadata" in table_names
        db.close()

    def test_schema_idempotent(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.initialize()
        db.initialize()

        conn = db.connect()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [row[0] for row in tables]
        assert "cards" in table_names
        db.close()

    def test_context_manager(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        with db as conn:
            conn.execute("SELECT 1")
        # Connection should still be open after context exit (reuse)
        assert db._conn is not None
        db.close()

    def test_foreign_keys_enabled(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        conn = db.connect()
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1
        db.close()

    def test_close_sets_none(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.connect()
        db.close()
        assert db._conn is None

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        nested_path = tmp_path / "a" / "b" / "c" / "test.db"
        db = Database(nested_path)
        db.connect()
        assert nested_path.exists()
        db.close()
