"""Trace and trace-step persistence."""

from __future__ import annotations

import json
from typing import Any

from mini_agent.domain.models import TraceRecord, TraceStepRecord

from .database import Database
from .session_repository import utc_now


def _json_loads(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {"value": decoded}


def _trace_from_row(row) -> TraceRecord | None:
    if row is None:
        return None
    return TraceRecord(
        id=row["id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        user_input=row["user_input"],
        status=row["status"],
        total_steps=row["total_steps"],
        total_prompt_tokens=row["total_prompt_tokens"],
        total_completion_tokens=row["total_completion_tokens"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error_code=row["error_code"],
        error_message=row["error_message"],
    )


class TraceRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(
        self,
        trace_id: str,
        user_id: str,
        session_id: str,
        user_input: str,
        status: str = "running",
    ) -> TraceRecord:
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO traces(
                    id, user_id, session_id, user_input, status, started_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (trace_id, user_id, session_id, user_input, status, utc_now()),
            )
        record = self.get(trace_id)
        assert record is not None
        return record

    def get(self, trace_id: str) -> TraceRecord | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM traces WHERE id = ?",
                (trace_id,),
            ).fetchone()
        return _trace_from_row(row)

    def get_latest(self, user_id: str, session_id: str) -> TraceRecord | None:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM traces
                WHERE user_id = ? AND session_id = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (user_id, session_id),
            ).fetchone()
        return _trace_from_row(row)

    def finish(
        self,
        trace_id: str,
        *,
        status: str,
        total_steps: int,
        total_prompt_tokens: int,
        total_completion_tokens: int,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE traces
                SET status = ?, total_steps = ?,
                    total_prompt_tokens = ?, total_completion_tokens = ?,
                    finished_at = ?, error_code = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    status,
                    total_steps,
                    total_prompt_tokens,
                    total_completion_tokens,
                    utc_now(),
                    error_code,
                    error_message,
                    trace_id,
                ),
            )

    def add_step(
        self,
        *,
        trace_id: str,
        step_number: int,
        event_index: int,
        event_type: str,
        status: str,
        name: str | None = None,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> int:
        with self.database.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trace_steps(
                    trace_id, step_number, event_index, event_type,
                    name, input_json, output_json, status, duration_ms,
                    error_code, error_message, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    step_number,
                    event_index,
                    event_type,
                    name,
                    json.dumps(input_data, ensure_ascii=False) if input_data is not None else None,
                    (
                        json.dumps(output_data, ensure_ascii=False)
                        if output_data is not None
                        else None
                    ),
                    status,
                    duration_ms,
                    error_code,
                    error_message,
                    utc_now(),
                ),
            )
        return int(cursor.lastrowid)

    def list_steps(self, trace_id: str) -> list[TraceStepRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM trace_steps
                WHERE trace_id = ?
                ORDER BY step_number, event_index, id
                """,
                (trace_id,),
            ).fetchall()
        return [
            TraceStepRecord(
                id=row["id"],
                trace_id=row["trace_id"],
                step_number=row["step_number"],
                event_index=row["event_index"],
                event_type=row["event_type"],
                name=row["name"],
                input_data=_json_loads(row["input_json"]),
                output_data=_json_loads(row["output_json"]),
                status=row["status"],
                duration_ms=row["duration_ms"],
                error_code=row["error_code"],
                error_message=row["error_message"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
