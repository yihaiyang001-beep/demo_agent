from __future__ import annotations

from typing import Any

import pytest

from mini_agent.bootstrap import build_application
from mini_agent.config import Config
from mini_agent.domain.models import LLMResponse, ToolCall, ToolRuntimeContext
from mini_agent.storage.database import Database
from mini_agent.storage.session_repository import SessionRepository
from mini_agent.tools.base import BaseTool, ToolArgs
from mini_agent.tools.registry import ToolRegistry
from tests.fakes.scripted_llm import ScriptedLLM


def pending_call():
    return ToolCall(
        id="old_call",
        name="calculator",
        arguments={"expression": "1 + 1"},
        raw_arguments='{"expression":"1 + 1"}',
    )


def test_runtime_can_continue_after_repair(tmp_path):
    llm = ScriptedLLM([LLMResponse(content="已继续。")])
    app = build_application(
        Config(api_key="repair-test", db_path=str(tmp_path / "agent.db")),
        llm_client=llm,
    )
    app.session_service.create("user_a", "window_1")
    app.message_repo.add_assistant_tool_calls(
        "user_a",
        "window_1",
        [pending_call()],
    )

    result = app.runtime.run("user_a", "window_1", "继续")

    assert result.status == "completed"
    request_messages = llm.requests[0]["messages"]
    old_assistant_index = next(
        index
        for index, message in enumerate(request_messages)
        if message.get("tool_calls")
    )
    assert request_messages[old_assistant_index + 1]["role"] == "tool"
    assert request_messages[old_assistant_index + 2]["content"] == "继续"
    steps = app.trace_repo.list_steps(result.trace_id)
    assert any(step.event_type == "tool_calls_repaired" for step in steps)


class InterruptArgs(ToolArgs):
    pass


class InterruptTool(BaseTool):
    name = "interrupt"
    description = "Raise KeyboardInterrupt"
    args_model = InterruptArgs

    def execute(self, args: ToolArgs, context: ToolRuntimeContext) -> dict[str, Any]:
        raise KeyboardInterrupt


def test_keyboard_interrupt_repairs_current_tool_call(tmp_path):
    registry = ToolRegistry()
    registry.register(InterruptTool())
    current_call = ToolCall(
        id="current_call",
        name="interrupt",
        arguments={},
        raw_arguments="{}",
    )
    app = build_application(
        Config(api_key="interrupt-test", db_path=str(tmp_path / "agent.db")),
        llm_client=ScriptedLLM(
            [LLMResponse(content="", tool_calls=[current_call])]
        ),
        tool_registry=registry,
    )

    with pytest.raises(KeyboardInterrupt):
        app.runtime.run("user_a", "window_1", "interrupt now")

    pending = app.message_repo.find_pending_tool_calls("user_a", "window_1")
    records = app.message_repo.list_messages("user_a", "window_1")
    session = app.session_service.switch("user_a", "window_1")
    trace = app.trace_repo.get_latest("user_a", "window_1")
    assert pending == []
    assert json_error_code(records[-1].content) == "INTERRUPTED"
    assert session.status == "idle"
    assert trace.status == "interrupted"


def json_error_code(content):
    import json

    return json.loads(content)["error_code"]


def test_stale_busy_session_is_recovered(tmp_path):
    db_path = tmp_path / "agent.db"
    database = Database(str(db_path))
    database.initialize()
    sessions = SessionRepository(database)
    sessions.create("user_a", "window_1")
    sessions.set_status("user_a", "window_1", "busy")

    app = build_application(
        Config(api_key="startup-test", db_path=str(db_path)),
        llm_client=ScriptedLLM([]),
    )

    assert app.session_service.switch("user_a", "window_1").status == "idle"
    trace = app.trace_repo.get_latest("user_a", "window_1")
    assert trace.status == "completed"
    assert app.trace_repo.list_steps(trace.id)[0].event_type == "stale_busy_recovered"

