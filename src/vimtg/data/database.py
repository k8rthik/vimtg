import sqlite3
from pathlib import Path


class Database:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> sqlite3.Connection:
        return self.connect()

    def __exit__(self, *args: object) -> None:
        pass  # Don't close on context exit -- reuse connection

    def initialize(self) -> None:
        from vimtg.data.schema import initialize_schema

        initialize_schema(self.connect())
