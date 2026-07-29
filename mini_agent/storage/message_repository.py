"""Conversation message persistence and OpenAI message reconstruction."""

from __future__ import annotations

import json
from typing import Any

from mini_agent.domain.errors import DatabaseOperationError
from mini_agent.domain.models import MessageRecord, ToolCall

from .database import Database
from .session_repository import utc_now


def _from_row(row) -> MessageRecord:
    tool_calls = None
    raw_tool_calls = row["tool_calls_json"]
    if raw_tool_calls:
        try:
            decoded = json.loads(raw_tool_calls)
        except json.JSONDecodeError as exc:
            raise DatabaseOperationError(
                f"Invalid tool_calls_json in message {row['id']}: {exc}"
            ) from exc
        if not isinstance(decoded, list):
            raise DatabaseOperationError(
                f"tool_calls_json in message {row['id']} is not a list"
            )
        tool_calls = decoded
    return MessageRecord(
        id=row["id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        tool_calls=tool_calls,
        tool_call_id=row["tool_call_id"],
        created_at=row["created_at"],
    )


class MessageRepository:
    def __init__(self, database: Database):
        self.database = database

    def _add(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        content: str | None,
        tool_calls_json: str | None = None,
        tool_call_id: str | None = None,
    ) -> int:
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages(
                    user_id, session_id, role, content,
                    tool_calls_json, tool_call_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    session_id,
                    role,
                    content,
                    tool_calls_json,
                    tool_call_id,
                    utc_now(),
                ),
            )
        return int(cursor.lastrowid)

    def add_user_message(self, user_id: str, session_id: str, content: str) -> int:
        return self._add(
            user_id=user_id,
            session_id=session_id,
            role="user",
            content=content,
        )

    def add_assistant_message(
        self,
        user_id: str,
        session_id: str,
        content: str,
    ) -> int:
        return self._add(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=content,
        )

    def add_assistant_tool_calls(
        self,
        user_id: str,
        session_id: str,
        tool_calls: list[ToolCall],
        content: str | None = None,
    ) -> int:
        payload = [tool_call.to_openai_dict() for tool_call in tool_calls]
        return self._add(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=content,
            tool_calls_json=json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )

    def add_tool_result(
        self,
        user_id: str,
        session_id: str,
        tool_call_id: str,
        content: str,
    ) -> int:
        return self._add(
            user_id=user_id,
            session_id=session_id,
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
        )

    def list_messages(self, user_id: str, session_id: str) -> list[MessageRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE user_id = ? AND session_id = ?
                ORDER BY id
                """,
                (user_id, session_id),
            ).fetchall()
        return [_from_row(row) for row in rows]

    def list_messages_after(
        self,
        user_id: str,
        session_id: str,
        message_id: int,
    ) -> list[MessageRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE user_id = ? AND session_id = ? AND id > ?
                ORDER BY id
                """,
                (user_id, session_id, message_id),
            ).fetchall()
        return [_from_row(row) for row in rows]

    def get_first_user_message(self, user_id: str, session_id: str) -> str | None:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT content FROM messages
                WHERE user_id = ? AND session_id = ? AND role = 'user'
                ORDER BY id
                LIMIT 1
                """,
                (user_id, session_id),
            ).fetchone()
        return row["content"] if row else None

    def count(self, user_id: str, session_id: str) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM messages
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()
        return int(row["count"])

    @staticmethod
    def to_api_messages(records: list[MessageRecord]) -> list[dict[str, Any]]:
        return [record.to_api_message() for record in records]

