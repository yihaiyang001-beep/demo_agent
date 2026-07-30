from __future__ import annotations

import json

import pytest

from mini_agent.config import Config
from mini_agent.context.manager import ContextManager
from mini_agent.context.token_estimator import SimpleTokenEstimator
from mini_agent.domain.errors import ContextLimitExceededError
from mini_agent.domain.models import LLMResponse, ToolCall
from mini_agent.session.service import SessionService
from mini_agent.storage.database import Database
from mini_agent.storage.message_repository import MessageRepository
from mini_agent.storage.session_repository import SessionRepository
from mini_agent.storage.summary_repository import SummaryRepository
from mini_agent.storage.trace_repository import TraceRepository
from mini_agent.tools.registry import ToolRegistry
from mini_agent.trace.recorder import TraceRecorder
from tests.fakes.scripted_llm import ScriptedLLM


def build_context(tmp_path, responses, **config_overrides):
    database = Database(str(tmp_path / "agent.db"))
    database.initialize()
    messages = MessageRepository(database)
    sessions = SessionRepository(database)
    summaries = SummaryRepository(database)
    service = SessionService(
        session_repo=sessions,
        summary_repo=summaries,
        message_repo=messages,
    )
    service.create("user_a", "window_1")
    config_values = {
        "api_key": "context-test",
        "db_path": str(tmp_path / "agent.db"),
        "max_context_tokens": 300,
        "summary_threshold_ratio": 0.7,
        "collapse_threshold_ratio": 0.9,
        "recent_messages": 4,
        "collapse_recent_messages": 2,
    }
    config_values.update(config_overrides)
    llm = ScriptedLLM(responses)
    manager = ContextManager(
        config=Config(**config_values),
        llm_client=llm,
        message_repo=messages,
        summary_repo=summaries,
        tool_registry=ToolRegistry(),
        trace_recorder=TraceRecorder(TraceRepository(database)),
        token_estimator=SimpleTokenEstimator(),
        system_prompt="sys",
    )
    return manager, messages, summaries, llm


def add_turn(messages, user_text, assistant_text):
    messages.add_user_message("user_a", "window_1", user_text)
    messages.add_assistant_message("user_a", "window_1", assistant_text)


def test_no_compression_below_threshold(tmp_path):
    manager, messages, summaries, llm = build_context(tmp_path, [])
    add_turn(messages, "hi", "hello")

    result = manager.prepare("user_a", "window_1")

    assert not result.compressed
    assert summaries.get("user_a", "window_1") is None
    assert llm.requests == []


def test_estimate_tokens_is_read_only_and_does_not_compress(tmp_path):
    manager, messages, summaries, llm = build_context(
        tmp_path,
        [LLMResponse(content="summary")],
    )
    for index in range(4):
        add_turn(messages, f"user-{index}-" + "x" * 80, f"assistant-{index}")
    before = messages.list_messages("user_a", "window_1")

    estimated = manager.estimate_tokens("user_a", "window_1")

    expected_messages = [
        {"role": "system", "content": "sys"},
        *messages.to_api_messages(before),
    ]
    expected = SimpleTokenEstimator().estimate_messages(expected_messages, [])
    assert estimated == expected
    assert estimated >= round(
        manager.config.max_context_tokens
        * manager.config.summary_threshold_ratio
    )
    assert summaries.get("user_a", "window_1") is None
    assert messages.list_messages("user_a", "window_1") == before
    assert llm.requests == []


def test_compression_triggered_at_70_percent(tmp_path):
    manager, messages, summaries, llm = build_context(
        tmp_path,
        [LLMResponse(content="累计摘要")],
    )
    for index in range(4):
        add_turn(messages, f"user-{index}-" + "x" * 80, f"assistant-{index}-" + "y" * 80)

    result = manager.prepare("user_a", "window_1")

    assert result.compressed
    assert summaries.get("user_a", "window_1").summary == "累计摘要"
    assert len(llm.requests) == 1
    assert llm.requests[0]["tools"] is None


def test_collapse_window_used_at_90_percent(tmp_path):
    manager, messages, _, _ = build_context(
        tmp_path,
        [LLMResponse(content="S")],
        max_context_tokens=160,
    )
    for index in range(4):
        add_turn(messages, f"user-{index}-" + "x" * 70, f"assistant-{index}-" + "y" * 70)

    result = manager.prepare("user_a", "window_1")
    non_system = result.messages[1:]

    assert result.estimated_tokens <= 160
    assert len(non_system) == 2
    assert non_system[0]["content"].startswith("user-3")


def test_raw_messages_are_not_modified_or_deleted(tmp_path):
    manager, messages, _, _ = build_context(
        tmp_path,
        [LLMResponse(content="summary")],
    )
    for index in range(4):
        add_turn(messages, f"raw-user-{index}-" + "x" * 80, f"raw-assistant-{index}")
    before = messages.list_messages("user_a", "window_1")

    manager.prepare("user_a", "window_1")
    after = messages.list_messages("user_a", "window_1")

    assert after == before
    assert messages.count("user_a", "window_1") == 8


def test_summary_boundary_is_persisted(tmp_path):
    manager, messages, summaries, _ = build_context(
        tmp_path,
        [LLMResponse(content="summary")],
    )
    for index in range(4):
        add_turn(messages, f"user-{index}-" + "x" * 80, f"assistant-{index}")

    manager.prepare("user_a", "window_1")
    summary = summaries.get("user_a", "window_1")

    assert summary.summarized_until_message_id > 0
    assert messages.list_messages_after(
        "user_a",
        "window_1",
        summary.summarized_until_message_id,
    )


def test_incremental_summary_does_not_repeat_old_history(tmp_path):
    manager, messages, _, llm = build_context(
        tmp_path,
        [LLMResponse(content="S1"), LLMResponse(content="S2")],
        max_context_tokens=10_000,
    )
    add_turn(messages, "UNIQUE_OLD_FACT", "old answer")
    add_turn(messages, "middle", "middle answer")
    manager.manual_compact("user_a", "window_1")
    add_turn(messages, "new fact", "new answer")
    add_turn(messages, "latest", "latest answer")

    manager.manual_compact("user_a", "window_1")

    second_summary_input = llm.requests[1]["messages"][1]["content"]
    assert "[PREVIOUS SUMMARY]\nS1" in second_summary_input
    assert "UNIQUE_OLD_FACT" not in second_summary_input


def test_summary_is_injected_into_system_context(tmp_path):
    manager, messages, summaries, _ = build_context(tmp_path, [])
    add_turn(messages, "old", "answer")
    boundary = messages.list_messages("user_a", "window_1")[-1].id
    summaries.upsert("user_a", "window_1", "杭州，8 月 10 日", boundary)
    add_turn(messages, "现在继续", "好的")

    result = manager.prepare("user_a", "window_1")

    assert "[SESSION SUMMARY]" in result.messages[0]["content"]
    assert "杭州，8 月 10 日" in result.messages[0]["content"]
    assert result.messages[1]["content"] == "现在继续"


def test_todo_data_is_not_put_into_summary_input(tmp_path):
    manager, messages, _, llm = build_context(
        tmp_path,
        [LLMResponse(content="summary")],
        max_context_tokens=10_000,
    )
    messages.add_user_message("user_a", "window_1", "维护待办")
    todo_call = ToolCall(
        id="call_todo",
        name="todo",
        arguments={"action": "add", "content": "SECRET_TODO"},
        raw_arguments='{"action":"add","content":"SECRET_TODO"}',
    )
    messages.add_assistant_tool_calls("user_a", "window_1", [todo_call])
    messages.add_tool_result(
        "user_a",
        "window_1",
        "call_todo",
        json.dumps({"data": {"content": "SECRET_TODO"}}),
    )
    messages.add_assistant_message("user_a", "window_1", "已添加")
    add_turn(messages, "下一话题", "继续")

    manager.manual_compact("user_a", "window_1")

    summary_input = llm.requests[0]["messages"][1]["content"]
    assert "SECRET_TODO" not in summary_input


def test_compression_failure_keeps_old_summary(tmp_path):
    manager, messages, summaries, _ = build_context(
        tmp_path,
        [RuntimeError("summary unavailable")],
        max_context_tokens=10_000,
    )
    add_turn(messages, "old", "answer")
    boundary = messages.list_messages("user_a", "window_1")[-1].id
    summaries.upsert("user_a", "window_1", "OLD SUMMARY", boundary)
    add_turn(messages, "new one", "answer one")
    add_turn(messages, "new two", "answer two")

    result = manager.manual_compact("user_a", "window_1")

    assert not result.compressed
    assert summaries.get("user_a", "window_1").summary == "OLD SUMMARY"


def test_manual_compact_command_path(tmp_path):
    manager, messages, summaries, _ = build_context(
        tmp_path,
        [LLMResponse(content="manual summary")],
        max_context_tokens=10_000,
    )
    add_turn(messages, "first", "one")
    add_turn(messages, "second", "two")

    result = manager.manual_compact("user_a", "window_1")

    assert result.compressed
    assert summaries.get("user_a", "window_1").summary == "manual summary"


def test_long_tool_result_is_truncated_only_in_context(tmp_path):
    manager, messages, _, _ = build_context(
        tmp_path,
        [],
        max_context_tokens=300,
    )
    messages.add_user_message("user_a", "window_1", "search")
    call = ToolCall(
        id="call_search",
        name="search",
        arguments={"query": "agent"},
        raw_arguments='{"query":"agent"}',
    )
    messages.add_assistant_tool_calls("user_a", "window_1", [call])
    raw_result = json.dumps({"success": True, "data": "z" * 3000})
    messages.add_tool_result(
        "user_a",
        "window_1",
        "call_search",
        raw_result,
    )
    messages.add_assistant_message("user_a", "window_1", "done")

    result = manager.prepare("user_a", "window_1")

    context_tool = next(item for item in result.messages if item["role"] == "tool")
    assert json.loads(context_tool["content"])["error_code"] == (
        "CONTEXT_TOOL_RESULT_TRUNCATED"
    )
    stored_tool = next(
        item
        for item in messages.list_messages("user_a", "window_1")
        if item.role == "tool"
    )
    assert stored_tool.content == raw_result
    assert result.estimated_tokens <= 300


def test_unshrinkable_context_raises_limit_error(tmp_path):
    manager, messages, _, _ = build_context(
        tmp_path,
        [],
        max_context_tokens=100,
    )
    add_turn(messages, "u" * 2000, "a")

    with pytest.raises(ContextLimitExceededError):
        manager.prepare("user_a", "window_1")
