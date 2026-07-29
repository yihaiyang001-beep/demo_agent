"""Non-streaming DeepSeek Chat Completions adapter."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from mini_agent.config import Config
from mini_agent.domain.errors import LLMBadRequestError, LLMUnavailableError
from mini_agent.domain.models import LLMResponse, ToolCall

RetryObserver = Callable[[int, str, int], None]


class DeepSeekClient:
    def __init__(
        self,
        config: Config,
        *,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        on_retry: RetryObserver | None = None,
    ):
        self.config = config
        self.client = client or OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.llm_timeout_seconds,
        )
        self._sleep = sleep
        self._on_retry = on_retry

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        params: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "max_tokens": self.config.max_output_tokens,
            "temperature": self.config.temperature,
            "extra_body": {
                "thinking": {
                    "type": "enabled" if self.config.thinking_enabled else "disabled"
                }
            },
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        started = time.perf_counter()
        response = self._call_with_retry(params)
        duration_ms = round((time.perf_counter() - started) * 1000)

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMUnavailableError("DeepSeek response contained no choices")

        choice = choices[0]
        message = choice.message
        parsed_tool_calls = [
            self._parse_tool_call(raw_call)
            for raw_call in (getattr(message, "tool_calls", None) or [])
        ]
        usage = getattr(response, "usage", None)
        raw_message = self._safe_model_dump(message)

        return LLMResponse(
            content=getattr(message, "content", None) or "",
            tool_calls=parsed_tool_calls,
            prompt_tokens=(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0,
            completion_tokens=(getattr(usage, "completion_tokens", 0) or 0) if usage else 0,
            finish_reason=getattr(choice, "finish_reason", None),
            raw_message=raw_message,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _parse_tool_call(raw_call: Any) -> ToolCall:
        raw_arguments = getattr(raw_call.function, "arguments", None) or "{}"
        parse_error = None
        arguments: dict[str, Any] | None
        try:
            decoded = json.loads(raw_arguments)
            if not isinstance(decoded, dict):
                arguments = None
                parse_error = "Tool arguments must be a JSON object"
            else:
                arguments = decoded
        except (json.JSONDecodeError, TypeError) as exc:
            arguments = None
            parse_error = str(exc)

        return ToolCall(
            id=str(getattr(raw_call, "id", "")),
            name=str(getattr(raw_call.function, "name", "")),
            arguments=arguments,
            raw_arguments=raw_arguments,
            parse_error=parse_error,
        )

    @staticmethod
    def _safe_model_dump(message: Any) -> dict[str, Any] | None:
        model_dump = getattr(message, "model_dump", None)
        if not callable(model_dump):
            return None
        dumped = model_dump(exclude_none=True)
        return dumped if isinstance(dumped, dict) else None

    def _call_with_retry(self, params: dict[str, Any]) -> Any:
        non_retryable = (
            AuthenticationError,
            BadRequestError,
            NotFoundError,
            PermissionDeniedError,
            UnprocessableEntityError,
        )
        transient = (RateLimitError, APITimeoutError, APIConnectionError)

        for attempt in range(1, self.config.llm_max_retries + 1):
            try:
                return self.client.chat.completions.create(**params)
            except non_retryable as exc:
                raise LLMBadRequestError(
                    f"{type(exc).__name__}: {exc}",
                ) from exc
            except transient as exc:
                if attempt >= self.config.llm_max_retries:
                    raise LLMUnavailableError(
                        f"{type(exc).__name__} after {attempt} attempts"
                    ) from exc
                self._retry_after(attempt, exc)
            except APIError as exc:
                status_code = getattr(exc, "status_code", None)
                if status_code is not None and status_code >= 500:
                    if attempt >= self.config.llm_max_retries:
                        raise LLMUnavailableError(
                            f"{type(exc).__name__} after {attempt} attempts"
                        ) from exc
                    self._retry_after(attempt, exc)
                else:
                    raise LLMBadRequestError(
                        f"{type(exc).__name__}: request rejected"
                    ) from exc

        raise LLMUnavailableError("DeepSeek retry loop ended unexpectedly")

    def _retry_after(self, attempt: int, exc: Exception) -> None:
        delay_seconds = 2 ** (attempt - 1)
        if self._on_retry:
            self._on_retry(attempt, type(exc).__name__, delay_seconds * 1000)
        self._sleep(delay_seconds)

