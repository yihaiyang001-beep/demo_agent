from __future__ import annotations

import sqlite3

import pytest

from mini_agent.storage.database import Database

EXPECTED_TABLES = {
    "sessions",
    "messages",
    "session_summaries",
    "todos",
    "traces",
    "trace_steps",
}


def test_database_creates_all_tables(tmp_path):
    database = Database(str(tmp_path / "agent.db"))
    database.initialize()

    with database.connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    assert EXPECTED_TABLES.issubset({row["name"] for row in rows})
    assert database.is_initialized()


def test_database_enables_foreign_keys(tmp_path):
    database = Database(str(tmp_path / "agent.db"))
    database.initialize()

    with database.connect() as conn:
        enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]

    assert enabled == 1


def test_database_creates_parent_directory(tmp_path):
    db_path = tmp_path / "deep" / "nested" / "agent.db"
    database = Database(str(db_path))

    database.initialize()

    assert db_path.is_file()


def test_database_initialize_is_idempotent(tmp_path):
    database = Database(str(tmp_path / "agent.db"))

    database.initialize()
    database.initialize()

    assert database.is_initialized()


def test_database_context_manager_closes_connection(tmp_path):
    database = Database(str(tmp_path / "agent.db"))
    database.initialize()

    with database.connect() as connection:
        connection.execute("SELECT 1").fetchone()

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
