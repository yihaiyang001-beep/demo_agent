from __future__ import annotations

from typing import Any

import pytest
from pydantic import Field

from mini_agent.domain.errors import DuplicateToolError
from mini_agent.domain.models import ToolCall, ToolRuntimeContext
from mini_agent.tools.base import BaseTool, ToolArgs
from mini_agent.tools.registry import ToolRegistry


class EchoArgs(ToolArgs):
    text: str = Field(min_length=1)


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo text"
    args_model = EchoArgs

    def execute(self, args: ToolArgs, context: ToolRuntimeContext) -> dict[str, Any]:
        assert isinstance(args, EchoArgs)
        return {"text": args.text}


def call(name="echo", arguments=None, parse_error=None):
    return ToolCall(
        id="call_1",
        name=name,
        arguments={"text": "hello"} if arguments is None else arguments,
        raw_arguments='{"text":"hello"}',
        parse_error=parse_error,
    )


def test_register_and_lookup_tool(runtime_context):
    registry = ToolRegistry()
    tool = EchoTool()
    registry.register(tool)

    assert registry.get("echo") is tool
    result = registry.execute(call(), runtime_context)
    assert result.success
    assert result.content == {"text": "hello"}


def test_duplicate_tool_name_rejected():
    registry = ToolRegistry()
    registry.register(EchoTool())

    with pytest.raises(DuplicateToolError):
        registry.register(EchoTool())


def test_schemas_are_openai_compatible():
    registry = ToolRegistry()
    registry.register(EchoTool())

    schema = registry.schemas()[0]

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "echo"
    assert schema["function"]["parameters"]["type"] == "object"
    assert schema["function"]["parameters"]["additionalProperties"] is False
    assert "text" in schema["function"]["parameters"]["required"]


def test_unknown_tool_returns_structured_error(runtime_context):
    registry = ToolRegistry()

    result = registry.execute(call(name="missing"), runtime_context)

    assert not result.success
    assert result.error_code == "UNKNOWN_TOOL"
    assert "missing" in (result.error_message or "")


@pytest.mark.parametrize(
    "tool_call",
    [
        call(arguments={}),
        call(arguments={"text": "hello", "extra": True}),
        call(arguments=None, parse_error="invalid JSON"),
    ],
)
def test_invalid_arguments_returns_structured_error(runtime_context, tool_call):
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = registry.execute(tool_call, runtime_context)

    assert not result.success
    assert result.error_code == "INVALID_TOOL_ARGUMENTS"

