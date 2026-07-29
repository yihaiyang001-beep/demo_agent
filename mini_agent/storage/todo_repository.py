"""Session-scoped Todo persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .database import Database


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _todo_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "content": row["content"],
        "status": row["status"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
    }


class TodoRepository:
    def __init__(self, database: Database):
        self.database = database

    def add(self, user_id: str, session_id: str, content: str) -> dict[str, Any]:
        created_at = _utc_now()
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO todos(user_id, session_id, content, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (user_id, session_id, content, created_at),
            )
            row = conn.execute(
                "SELECT * FROM todos WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        return _todo_dict(row)

    def list(
        self,
        user_id: str,
        session_id: str,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM todos WHERE user_id = ? AND session_id = ?"
        params: list[Any] = [user_id, session_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id"
        with self.database.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_todo_dict(row) for row in rows]

    def complete(
        self,
        user_id: str,
        session_id: str,
        todo_id: int,
    ) -> dict[str, Any] | None:
        completed_at = _utc_now()
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE todos
                SET status = 'completed', completed_at = ?
                WHERE id = ? AND user_id = ? AND session_id = ?
                """,
                (completed_at, todo_id, user_id, session_id),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                """
                SELECT * FROM todos
                WHERE id = ? AND user_id = ? AND session_id = ?
                """,
                (todo_id, user_id, session_id),
            ).fetchone()
        return _todo_dict(row)

    def delete(self, user_id: str, session_id: str, todo_id: int) -> bool:
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM todos
                WHERE id = ? AND user_id = ? AND session_id = ?
                """,
                (todo_id, user_id, session_id),
            )
        return cursor.rowcount > 0

