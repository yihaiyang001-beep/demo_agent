from __future__ import annotations

import json

from mini_agent.bootstrap import build_application
from mini_agent.config import Config
from mini_agent.domain.models import LLMResponse, ToolCall
from tests.fakes.scripted_llm import ScriptedLLM


def tool_call(call_id, name, arguments):
    raw = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
    return ToolCall(
        id=call_id,
        name=name,
        arguments=arguments,
        raw_arguments=raw,
    )


def response(content="", calls=None, prompt_tokens=10, completion_tokens=5):
    return LLMResponse(
        content=content,
        tool_calls=calls or [],
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        finish_reason="tool_calls" if calls else "stop",
    )


def make_application(tmp_path, responses, **config_overrides):
    values = {
        "api_key": "runtime-test",
        "db_path": str(tmp_path / "agent.db"),
        "max_steps": 8,
        "repeat_limit": 2,
    }
    values.update(config_overrides)
    llm = ScriptedLLM(responses)
    return build_application(Config(**values), llm_client=llm), llm


def test_direct_answer(tmp_path):
    application, llm = make_application(tmp_path, [response("你好，我是 Mini Agent。")])

    result = application.runtime.run("user_a", "window_1", "你好")

    assert result.status == "completed"
    assert result.steps == 1
    assert len(llm.requests) == 1
    records = application.message_repo.list_messages("user_a", "window_1")
    assert [record.role for record in records] == ["user", "assistant"]
    assert records[-1].content == "你好，我是 Mini Agent。"


def test_single_tool_call(tmp_path):
    application, llm = make_application(
        tmp_path,
        [
            response(calls=[tool_call("call_1", "calculator", {"expression": "2 + 3"})]),
            response("结果是 5。"),
        ],
    )

    result = application.runtime.run("user_a", "window_1", "计算 2+3")

    assert result.status == "completed"
    assert result.steps == 2
    assert len(llm.requests) == 2
    second_messages = llm.requests[1]["messages"]
    assert second_messages[-2]["tool_calls"][0]["id"] == "call_1"
    assert second_messages[-1]["role"] == "tool"
    assert json.loads(second_messages[-1]["content"])["data"]["result"] == 5
    records = application.message_repo.list_messages("user_a", "window_1")
    assert [record.role for record in records] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


def test_multi_round_tools(tmp_path):
    application, _ = make_application(
        tmp_path,
        [
            response(
                calls=[
                    tool_call(
                        "call_search",
                        "search",
                        {"query": "agent runtime", "top_k": 1},
                    )
                ]
            ),
            response(
                calls=[
                    tool_call(
                        "call_todo",
                        "todo",
                        {"action": "add", "content": "完成 Agent Runtime 测试"},
                    )
                ]
            ),
            response("已搜索并添加待办。"),
        ],
    )

    result = application.runtime.run("user_a", "window_1", "搜索并记录待办")

    assert result.status == "completed"
    assert result.steps == 3
    todos = application.todo_repo.list("user_a", "window_1")
    assert todos[0]["content"] == "完成 Agent Runtime 测试"


def test_multiple_tools_in_one_response_execute_in_order(tmp_path):
    application, llm = make_application(
        tmp_path,
        [
            response(
                calls=[
                    tool_call("call_calc", "calculator", {"expression": "6 * 7"}),
                    tool_call("call_search", "search", {"query": "context"}),
                ]
            ),
            response("两个工具均已完成。"),
        ],
    )
    events = []

    result = application.runtime.run(
        "user_a",
        "window_1",
        "计算并搜索",
        on_tool_event=lambda event, name, details: events.append((event, name, details)),
    )

    assert result.status == "completed"
    assert [(event, name) for event, name, _ in events] == [
        ("call", "calculator"),
        ("result", "calculator"),
        ("call", "search"),
        ("result", "search"),
    ]
    tool_messages = [
        message
        for message in llm.requests[1]["messages"]
        if message["role"] == "tool"
    ]
    assert [message["tool_call_id"] for message in tool_messages] == [
        "call_calc",
        "call_search",
    ]


def test_max_steps(tmp_path):
    calls = [
        response(
            calls=[
                tool_call(
                    f"call_{index}",
                    "search",
                    {"query": f"agent {index}"},
                )
            ]
        )
        for index in range(3)
    ]
    application, llm = make_application(tmp_path, calls, max_steps=3)

    result = application.runtime.run("user_a", "window_1", "一直搜索")

    assert result.status == "max_steps_exceeded"
    assert result.steps == 3
    assert len(llm.requests) == 3
    assert application.trace_repo.get(result.trace_id).status == "max_steps_exceeded"


def test_third_repeated_tool_call_is_returned_as_error(tmp_path):
    repeated = [
        response(
            calls=[
                tool_call(
                    f"call_{index}",
                    "calculator",
                    {"expression": "1 + 1"},
                )
            ]
        )
        for index in range(3)
    ]
    application, llm = make_application(
        tmp_path,
        [*repeated, response("已停止重复调用。")],
        max_steps=4,
    )

    result = application.runtime.run("user_a", "window_1", "重复计算")

    assert result.status == "completed"
    fourth_request = llm.requests[3]["messages"]
    last_tool_result = json.loads(fourth_request[-1]["content"])
    assert last_tool_result["success"] is False
    assert last_tool_result["error_code"] == "REPEATED_TOOL_CALL"
    assert len(application.trace_repo.list_steps(result.trace_id)) > 0

