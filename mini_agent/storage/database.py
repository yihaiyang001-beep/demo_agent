"""SQLite connection and schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class ManagedConnection(sqlite3.Connection):
    """Commit/rollback like sqlite3, then also release the file handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, db_path: str):
        if not db_path:
            raise ValueError("db_path must not be empty")
        self.db_path = db_path

    def _ensure_parent(self) -> None:
        if self.db_path == ":memory:":
            return
        Path(self.db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        self._ensure_parent()
        conn = sqlite3.connect(
            self.db_path,
            timeout=5.0,
            factory=ManagedConnection,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def initialize(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        schema = schema_path.read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(schema)

    def is_initialized(self) -> bool:
        required = {
            "sessions",
            "messages",
            "session_summaries",
            "todos",
            "traces",
            "trace_steps",
        }
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        return required.issubset({row["name"] for row in rows})
