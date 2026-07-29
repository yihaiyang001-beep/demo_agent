"""Session metadata persistence using the composite owner key."""

from __future__ import annotations

from datetime import UTC, datetime

from mini_agent.domain.models import SessionRecord

from .database import Database


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _from_row(row) -> SessionRecord | None:
    if row is None:
        return None
    return SessionRecord(
        user_id=row["user_id"],
        id=row["id"],
        title=row["title"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SessionRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(
        self,
        user_id: str,
        session_id: str,
        title: str | None = None,
    ) -> SessionRecord:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(user_id, id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, session_id, title, now, now),
            )
        record = self.get(user_id, session_id)
        assert record is not None
        return record

    def get(self, user_id: str, session_id: str) -> SessionRecord | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE user_id = ? AND id = ?",
                (user_id, session_id),
            ).fetchone()
        return _from_row(row)

    def list_by_user(self, user_id: str, limit: int = 50) -> list[SessionRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ?
                ORDER BY updated_at DESC, id ASC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [_from_row(row) for row in rows if row is not None]

    def update_title_if_empty(
        self,
        user_id: str,
        session_id: str,
        title: str,
    ) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET title = CASE
                    WHEN title IS NULL OR trim(title) = '' THEN ?
                    ELSE title
                END,
                updated_at = ?
                WHERE user_id = ? AND id = ?
                """,
                (title, utc_now(), user_id, session_id),
            )

    def touch(self, user_id: str, session_id: str) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE sessions SET updated_at = ?
                WHERE user_id = ? AND id = ?
                """,
                (utc_now(), user_id, session_id),
            )

    def set_status(self, user_id: str, session_id: str, status: str) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE sessions SET status = ?, updated_at = ?
                WHERE user_id = ? AND id = ?
                """,
                (status, utc_now(), user_id, session_id),
            )

    def list_by_status(self, status: str) -> list[SessionRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sessions
                WHERE status = ?
                ORDER BY updated_at, user_id, id
                """,
                (status,),
            ).fetchall()
        return [_from_row(row) for row in rows if row is not None]

    def reset_status(self, from_status: str, to_status: str) -> list[SessionRecord]:
        records = self.list_by_status(from_status)
        if not records:
            return []
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status = ?, updated_at = ?
                WHERE status = ?
                """,
                (to_status, utc_now(), from_status),
            )
        return records
