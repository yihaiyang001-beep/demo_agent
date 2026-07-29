from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mini_agent.domain.models import ToolRuntimeContext
from mini_agent.storage.database import Database


@pytest.fixture
def runtime_context():
    return ToolRuntimeContext(
        user_id="user_a",
        session_id="window_1",
        trace_id="trace_test",
    )


@pytest.fixture
def todo_database(tmp_path):
    database = Database(str(tmp_path / "agent.db"))
    database.initialize()
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    with database.connect() as conn:
        conn.executemany(
            """
            INSERT INTO sessions(user_id, id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("user_a", "window_1", now, now),
                ("user_a", "window_2", now, now),
                ("user_b", "window_1", now, now),
            ],
        )
    return database

