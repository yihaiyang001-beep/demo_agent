"""Consecutive identical Tool Call protection."""

from __future__ import annotations

import json

from mini_agent.domain.models import ToolCall


def tool_call_fingerprint(call: ToolCall) -> str:
    payload = call.arguments if call.arguments is not None else call.raw_arguments
    normalized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{call.name}:{normalized}"


class RepetitionGuard:
    def __init__(self, limit: int):
        if limit < 1:
            raise ValueError("repeat limit must be at least 1")
        self.limit = limit
        self._last_fingerprint: str | None = None
        self._consecutive_count = 0

    def should_block(self, call: ToolCall) -> bool:
        fingerprint = tool_call_fingerprint(call)
        if fingerprint == self._last_fingerprint:
            self._consecutive_count += 1
        else:
            self._last_fingerprint = fingerprint
            self._consecutive_count = 1
        return self._consecutive_count > self.limit

