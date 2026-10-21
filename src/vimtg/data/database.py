import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from vimtg.data.search_sql import register_functions


class Database:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._conn: sqlite3.Connection | None = None
        # Read-only connections for concurrent searches. A sqlite3
        # connection must never run two statements from different
        # threads at once (InterfaceError), so each search checks one
        # out for itself; the pool grows only to the peak concurrency.
        self._lock = threading.Lock()
        self._idle_readers: list[sqlite3.Connection] = []
        self._busy_readers: set[sqlite3.Connection] = set()
        self._closed = False

    def _open(self) -> sqlite3.Connection:
        if str(self._path) == ":memory:":
            # A plain ':memory:' is private to its connection, so the
            # reader pool would open empty databases; a named shared
            # cache (unique to this Database) gives every connection
            # the same tables. It lives while the main connection does.
            conn = sqlite3.connect(
                f"file:vimtg-{id(self)}?mode=memory&cache=shared",
                uri=True, check_same_thread=False,
            )
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._open()
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._closed = False
        return self._conn

    @contextmanager
    def reader(self) -> Iterator[sqlite3.Connection]:
        """A connection the calling thread has to itself for the block.

        Safe to use from any number of worker threads at once (WAL lets
        them read alongside the main connection's writes).
        """
        self.connect()  # the main connection sets up WAL first
        with self._lock:
            conn = self._idle_readers.pop() if self._idle_readers else None
        if conn is None:
            conn = self._open()
            register_functions(conn)
        with self._lock:
            self._busy_readers.add(conn)
        try:
            yield conn
        finally:
            with self._lock:
                self._busy_readers.discard(conn)
                keep = not self._closed
                if keep:
                    self._idle_readers.append(conn)
            if not keep:
                conn.close()

    def close(self) -> None:
        with self._lock:
            # Readers still in use close themselves when released.
            self._closed = True
            idle, self._idle_readers = self._idle_readers, []
        for conn in idle:
            conn.close()
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
