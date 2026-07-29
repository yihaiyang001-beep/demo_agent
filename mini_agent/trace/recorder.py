"""Repository-backed recorder for observable runtime decisions."""

from __future__ import annotations

import contextvars
import uuid
from typing import Any

from mini_agent.domain.models import LLMResponse, ToolCall, ToolResult
from mini_agent.storage.trace_repository import TraceRepository


class TraceRecorder:
    def __init__(
        self,
        repository: TraceRepository,
        *,
        sensitive_values: list[str] | None = None,
    ):
        self.repository = repository
        self._sensitive_values = [
            value for value in (sensitive_values or []) if len(value) >= 8
        ]
        self._active_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
            "active_trace_id",
            default=None,
        )
        self._active_step: contextvars.ContextVar[int] = contextvars.ContextVar(
            "active_trace_step",
            default=0,
        )

    def _redact_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        redacted = value
        for secret in self._sensitive_values:
            redacted = redacted.replace(secret, "[REDACTED]")
        return redacted

    def _redact_data(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: (
                    "[REDACTED]"
                    if key.lower() in {"api_key", "apikey", "authorization", "token"}
                    else self._redact_data(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_data(item) for item in value]
        if isinstance(value, str):
            return self._redact_text(value)
        return value

    def start(self, *, user_id: str, session_id: str, user_input: str) -> str:
        trace_id = f"trace_{uuid.uuid4().hex}"
        self.repository.create(
            trace_id,
            user_id,
            session_id,
            self._redact_text(user_input) or "",
        )
        return trace_id

    def begin_llm_step(self, trace_id: str, step_number: int) -> None:
        self._active_trace_id.set(trace_id)
        self._active_step.set(step_number)

    def end_llm_step(self) -> None:
        self._active_trace_id.set(None)
        self._active_step.set(0)

    def record_retry(self, attempt: int, error_code: str, duration_ms: int) -> None:
        trace_id = self._active_trace_id.get()
        if trace_id is None:
            return
        self.repository.add_step(
            trace_id=trace_id,
            step_number=self._active_step.get(),
            event_index=1,
            event_type="retry",
            name="llm_request",
            status="retrying",
            output_data={"attempt": attempt},
            duration_ms=duration_ms,
            error_code=error_code,
        )

    def record_context(
        self,
        trace_id: str,
        step_number: int,
        estimated_tokens: int,
    ) -> None:
        self.repository.add_step(
            trace_id=trace_id,
            step_number=step_number,
            event_index=0,
            event_type="context_built",
            status="success",
            output_data={"estimated_tokens": estimated_tokens},
        )

    def record_llm_decision(
        self,
        trace_id: str,
        step_number: int,
        response: LLMResponse,
    ) -> None:
        decision = "tool_call" if response.tool_calls else "final_answer"
        self.repository.add_step(
            trace_id=trace_id,
            step_number=step_number,
            event_index=2,
            event_type="llm_decision",
            name=decision,
            status="success",
            output_data={
                "decision": decision,
                "tool_names": [call.name for call in response.tool_calls],
                "finish_reason": response.finish_reason,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
            },
            duration_ms=response.duration_ms,
        )

    def record_tool_call(
        self,
        trace_id: str,
        step_number: int,
        event_index: int,
        call: ToolCall,
    ) -> None:
        self.repository.add_step(
            trace_id=trace_id,
            step_number=step_number,
            event_index=event_index,
            event_type="tool_call",
            name=call.name,
            status="requested",
            input_data=self._redact_data(
                {
                    "arguments": call.arguments,
                    "raw_arguments": call.raw_arguments,
                    "parse_error": call.parse_error,
                }
            ),
        )

    def record_tool_result(
        self,
        trace_id: str,
        step_number: int,
        event_index: int,
        name: str,
        result: ToolResult,
    ) -> None:
        self.repository.add_step(
            trace_id=trace_id,
            step_number=step_number,
            event_index=event_index,
            event_type="tool_result",
            name=name,
            status="success" if result.success else "failed",
            output_data=self._redact_data(
                {
                    "success": result.success,
                    "data": result.content if result.success else None,
                }
            ),
            duration_ms=result.duration_ms,
            error_code=result.error_code,
            error_message=self._redact_text(result.error_message),
        )

    def record_event(
        self,
        trace_id: str,
        *,
        step_number: int,
        event_index: int,
        event_type: str,
        status: str,
        name: str | None = None,
        output_data: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.repository.add_step(
            trace_id=trace_id,
            step_number=step_number,
            event_index=event_index,
            event_type=event_type,
            name=name,
            status=status,
            output_data=self._redact_data(output_data),
            error_code=error_code,
            error_message=self._redact_text(error_message),
        )

    def complete(
        self,
        trace_id: str,
        *,
        steps: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        self.repository.finish(
            trace_id,
            status="completed",
            total_steps=steps,
            total_prompt_tokens=prompt_tokens,
            total_completion_tokens=completion_tokens,
        )

    def fail(
        self,
        trace_id: str,
        *,
        status: str,
        steps: int,
        prompt_tokens: int,
        completion_tokens: int,
        error_code: str,
        error_message: str,
    ) -> None:
        self.repository.finish(
            trace_id,
            status=status,
            total_steps=steps,
            total_prompt_tokens=prompt_tokens,
            total_completion_tokens=completion_tokens,
            error_code=error_code,
            error_message=self._redact_text(error_message),
        )
