from __future__ import annotations

import json

from mini_agent.domain.models import ToolCall


def add_pending_calls(storage):
    storage["session_repo"].create("user_a", "window_1")
    calls = [
        ToolCall(
            id="call_1",
            name="calculator",
            arguments={"expression": "1 + 1"},
            raw_arguments='{"expression":"1 + 1"}',
        ),
        ToolCall(
            id="call_2",
            name="search",
            arguments={"query": "agent"},
            raw_arguments='{"query":"agent"}',
        ),
    ]
    storage["message_repo"].add_assistant_tool_calls(
        "user_a",
        "window_1",
        calls,
    )
    return calls


def test_interrupt_backfills_all_missing_tool_results(storage):
    add_pending_calls(storage)

    repaired = storage["message_repo"].repair_pending_tool_calls(
        "user_a",
        "window_1",
    )

    assert repaired == ["call_1", "call_2"]
    tool_records = [
        record
        for record in storage["message_repo"].list_messages("user_a", "window_1")
        if record.role == "tool"
    ]
    assert [record.tool_call_id for record in tool_records] == ["call_1", "call_2"]
    assert all(
        json.loads(record.content)["error_code"] == "INTERRUPTED"
        for record in tool_records
    )


def test_existing_tool_result_is_not_duplicated(storage):
    add_pending_calls(storage)
    storage["message_repo"].add_tool_result(
        "user_a",
        "window_1",
        "call_1",
        '{"success":true}',
    )

    first_repair = storage["message_repo"].repair_pending_tool_calls(
        "user_a",
        "window_1",
    )
    second_repair = storage["message_repo"].repair_pending_tool_calls(
        "user_a",
        "window_1",
    )

    assert first_repair == ["call_2"]
    assert second_repair == []
    records = storage["message_repo"].list_messages("user_a", "window_1")
    assert [record.tool_call_id for record in records].count("call_1") == 1
    assert [record.tool_call_id for record in records].count("call_2") == 1


def test_repaired_history_is_api_valid(storage):
    add_pending_calls(storage)
    storage["message_repo"].repair_pending_tool_calls("user_a", "window_1")

    records = storage["message_repo"].list_messages("user_a", "window_1")
    api_messages = storage["message_repo"].to_api_messages(records)

    call_ids = {
        call["id"]
        for message in api_messages
        for call in message.get("tool_calls", [])
    }
    result_ids = {
        message["tool_call_id"]
        for message in api_messages
        if message["role"] == "tool"
    }
    assert call_ids == result_ids == {"call_1", "call_2"}

