"""Tool registration, validation, and safe execution."""

from __future__ import annotations

import time

from pydantic import ValidationError

from mini_agent.domain.errors import DuplicateToolError, ToolExecutionError
from mini_agent.domain.models import ToolCall, ToolResult, ToolRuntimeContext

from .base import BaseTool


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(tool.name)
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(
        self,
        tool_call: ToolCall,
        runtime_context: ToolRuntimeContext,
    ) -> ToolResult:
        started = time.perf_counter()
        if tool_call.parse_error or tool_call.arguments is None:
            return ToolResult(
                success=False,
                content={},
                error_code="INVALID_TOOL_ARGUMENTS",
                error_message=tool_call.parse_error or "工具参数不是合法 JSON 对象",
                duration_ms=_elapsed_ms(started),
            )

        tool = self._tools.get(tool_call.name)
        if tool is None:
            return ToolResult(
                success=False,
                content={},
                error_code="UNKNOWN_TOOL",
                error_message=f"未知工具：{tool_call.name}",
                duration_ms=_elapsed_ms(started),
            )

        try:
            args = tool.validate(tool_call.arguments)
        except ValidationError as exc:
            return ToolResult(
                success=False,
                content={},
                error_code="INVALID_TOOL_ARGUMENTS",
                error_message=str(exc),
                duration_ms=_elapsed_ms(started),
            )

        try:
            data = tool.execute(args, runtime_context)
            return ToolResult(
                success=True,
                content=data,
                duration_ms=_elapsed_ms(started),
            )
        except ToolExecutionError as exc:
            return ToolResult(
                success=False,
                content={},
                error_code=exc.code,
                error_message=exc.user_message,
                duration_ms=_elapsed_ms(started),
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                content={},
                error_code="TOOL_INTERNAL_ERROR",
                error_message=f"{type(exc).__name__}: {exc}",
                duration_ms=_elapsed_ms(started),
            )

