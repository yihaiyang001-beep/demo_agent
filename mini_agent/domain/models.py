"""Data exchanged across runtime boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] | None
    raw_arguments: str
    parse_error: str | None = None

    def to_openai_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.raw_arguments,
            },
        }


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str | None = None
    raw_message: dict[str, Any] | None = None
    duration_ms: int = 0


@dataclass
class ToolResult:
    success: bool
    content: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int = 0

    def to_message_content(self) -> str:
        return json.dumps(
            {
                "success": self.success,
                "data": self.content if self.success else None,
                "error_code": self.error_code,
                "message": self.error_message,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


@dataclass
class AgentResult:
    status: str
    answer: str
    trace_id: str
    steps: int
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class ToolRuntimeContext:
    user_id: str
    session_id: str
    trace_id: str

