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


@dataclass(frozen=True)
class SessionRecord:
    user_id: str
    id: str
    title: str | None
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SessionView:
    user_id: str
    id: str
    title: str | None
    preview: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MessageRecord:
    id: int
    user_id: str
    session_id: str
    role: str
    content: str | None
    tool_calls: list[dict[str, Any]] | None
    tool_call_id: str | None
    created_at: str

    def to_api_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.role == "assistant" and self.tool_calls:
            message["tool_calls"] = self.tool_calls
        if self.role == "tool" and self.tool_call_id:
            message["tool_call_id"] = self.tool_call_id
        return message


@dataclass(frozen=True)
class SummaryRecord:
    user_id: str
    session_id: str
    summary: str
    summarized_until_message_id: int
    updated_at: str


@dataclass(frozen=True)
class TraceRecord:
    id: str
    user_id: str
    session_id: str
    user_input: str
    status: str
    total_steps: int
    total_prompt_tokens: int
    total_completion_tokens: int
    started_at: str
    finished_at: str | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True)
class TraceStepRecord:
    id: int
    trace_id: str
    step_number: int
    event_index: int
    event_type: str
    name: str | None
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    status: str
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    created_at: str


@dataclass(frozen=True)
class ContextResult:
    messages: list[dict[str, Any]]
    estimated_tokens: int
    compressed: bool = False
