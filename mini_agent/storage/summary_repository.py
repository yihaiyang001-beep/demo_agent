"""Persistent cumulative session summaries."""

from __future__ import annotations

from mini_agent.domain.models import SummaryRecord

from .database import Database
from .session_repository import utc_now


class SummaryRepository:
    def __init__(self, database: Database):
        self.database = database

    def get(self, user_id: str, session_id: str) -> SummaryRecord | None:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM session_summaries
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()
        if row is None:
            return None
        return SummaryRecord(
            user_id=row["user_id"],
            session_id=row["session_id"],
            summary=row["summary"],
            summarized_until_message_id=row["summarized_until_message_id"],
            updated_at=row["updated_at"],
        )

    def upsert(
        self,
        user_id: str,
        session_id: str,
        summary: str,
        summarized_until_message_id: int,
    ) -> SummaryRecord:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO session_summaries(
                    user_id, session_id, summary,
                    summarized_until_message_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, session_id) DO UPDATE SET
                    summary = excluded.summary,
                    summarized_until_message_id =
                        excluded.summarized_until_message_id,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    session_id,
                    summary,
                    summarized_until_message_id,
                    utc_now(),
                ),
            )
        record = self.get(user_id, session_id)
        assert record is not None
        return record

