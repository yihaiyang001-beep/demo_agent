from __future__ import annotations

import json
from typing import Any

from mini_agent.bootstrap import build_application
from mini_agent.config import Config
from mini_agent.domain.errors import LLMUnavailableError
from mini_agent.domain.models import LLMResponse, ToolCall, ToolRuntimeContext
from mini_agent.tools.base import BaseTool, ToolArgs
from mini_agent.tools.registry import ToolRegistry
from tests.fakes.scripted_llm import ScriptedLLM


def make_call(name, arguments=None, *, parse_error=None):
    raw = json.dumps(arguments, ensure_ascii=False) if arguments is not None else "{bad"
    return ToolCall(
        id="call_1",
        name=name,
        arguments=arguments,
        raw_arguments=raw,
        parse_error=parse_error,
    )


def make_app(tmp_path, responses, *, api_key="runtime-secret", registry=None):
    llm = ScriptedLLM(responses)
    app = build_application(
        Config(api_key=api_key, db_path=str(tmp_path / "agent.db")),
        llm_client=llm,
        tool_registry=registry,
    )
    return app, llm


def test_unknown_tool_is_returned_to_llm(tmp_path):
    app, llm = make_app(
        tmp_path,
        [
            LLMResponse(tool_calls=[make_call("missing", {})], content=""),
            LLMResponse(content="该工具不可用。"),
        ],
        registry=ToolRegistry(),
    )

    result = app.runtime.run("user_a", "window_1", "调用未知工具")

    payload = json.loads(llm.requests[1]["messages"][-1]["content"])
    assert payload["error_code"] == "UNKNOWN_TOOL"
    assert result.status == "completed"


def test_invalid_tool_args_is_returned_to_llm(tmp_path):
    registry = ToolRegistry()
    app, llm = make_app(
        tmp_path,
        [
            LLMResponse(
                tool_calls=[
                    make_call(
                        "calculator",
                        None,
                        parse_error="invalid JSON",
                    )
                ],
                content="",
            ),
            LLMResponse(content="参数无效。"),
        ],
        registry=registry,
    )

    result = app.runtime.run("user_a", "window_1", "坏参数")

    payload = json.loads(llm.requests[1]["messages"][-1]["content"])
    assert payload["error_code"] == "INVALID_TOOL_ARGUMENTS"
    assert result.status == "completed"


class EmptyArgs(ToolArgs):
    pass


class ExplodingTool(BaseTool):
    name = "explode"
    description = "Raise an internal error"
    args_model = EmptyArgs

    def execute(self, args: ToolArgs, context: ToolRuntimeContext) -> dict[str, Any]:
        raise RuntimeError("tool exploded")


def test_tool_exception_is_returned_to_llm(tmp_path):
    registry = ToolRegistry()
    registry.register(ExplodingTool())
    app, llm = make_app(
        tmp_path,
        [
            LLMResponse(tool_calls=[make_call("explode", {})], content=""),
            LLMResponse(content="工具执行失败。"),
        ],
        registry=registry,
    )

    result = app.runtime.run("user_a", "window_1", "触发工具异常")

    payload = json.loads(llm.requests[1]["messages"][-1]["content"])
    assert payload["error_code"] == "TOOL_INTERNAL_ERROR"
    assert result.status == "completed"


def test_llm_timeout_after_retries_returns_trace_id(tmp_path):
    app, _ = make_app(
        tmp_path,
        [LLMUnavailableError("timeout after retries")],
        registry=ToolRegistry(),
    )

    result = app.runtime.run("user_a", "window_1", "你好")

    assert result.status == "llm_failed"
    assert result.trace_id in result.answer
    assert app.trace_repo.get(result.trace_id).status == "llm_failed"


def test_empty_llm_response(tmp_path):
    app, _ = make_app(
        tmp_path,
        [LLMResponse(content="")],
        registry=ToolRegistry(),
    )

    result = app.runtime.run("user_a", "window_1", "你好")

    assert result.status == "llm_failed"
    assert app.trace_repo.get(result.trace_id).error_code == "LLM_EMPTY_RESPONSE"


def test_database_error_returns_trace_id(tmp_path, monkeypatch):
    app, _ = make_app(
        tmp_path,
        [LLMResponse(content="最终回答")],
        registry=ToolRegistry(),
    )

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(app.message_repo, "add_assistant_message", fail_write)
    result = app.runtime.run("user_a", "window_1", "你好")

    assert result.status == "internal_error"
    assert result.trace_id in result.answer
    assert app.trace_repo.get(result.trace_id).error_code == "INTERNAL_ERROR"


def test_trace_records_failed_step(tmp_path):
    app, _ = make_app(
        tmp_path,
        [LLMUnavailableError("unavailable")],
        registry=ToolRegistry(),
    )

    result = app.runtime.run("user_a", "window_1", "你好")
    steps = app.trace_repo.list_steps(result.trace_id)

    assert any(
        step.event_type == "runtime_error" and step.status == "failed"
        for step in steps
    )


def test_api_key_never_appears_in_trace(tmp_path):
    secret = "super-secret-api-key"
    app, _ = make_app(
        tmp_path,
        [LLMUnavailableError(f"request with {secret} failed")],
        api_key=secret,
        registry=ToolRegistry(),
    )

    result = app.runtime.run("user_a", "window_1", f"do not log {secret}")
    trace = app.trace_repo.get(result.trace_id)
    steps = app.trace_repo.list_steps(result.trace_id)
    serialized = json.dumps(
        {
            "trace": trace.__dict__,
            "steps": [step.__dict__ for step in steps],
        },
        ensure_ascii=False,
    )

    assert secret not in serialized
    assert "[REDACTED]" in serialized

