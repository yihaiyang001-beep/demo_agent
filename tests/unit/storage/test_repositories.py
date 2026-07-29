from __future__ import annotations

import json

from mini_agent.domain.models import ToolCall


def test_create_and_get_session(storage):
    created = storage["session_repo"].create("user_a", "window_1")
    restored = storage["session_repo"].get("user_a", "window_1")

    assert restored == created
    assert restored.status == "idle"


def test_same_session_id_can_be_isolated_by_user_if_using_composite_key(storage):
    repo = storage["session_repo"]
    repo.create("user_a", "shared")
    repo.create("user_b", "shared")

    assert repo.get("user_a", "shared").user_id == "user_a"
    assert repo.get("user_b", "shared").user_id == "user_b"


def test_user_cannot_switch_to_other_user_session(storage):
    storage["session_repo"].create("user_b", "private")

    try:
        storage["service"].switch("user_a", "private")
    except Exception as exc:
        assert getattr(exc, "code", None) == "SESSION_NOT_FOUND"
    else:
        raise AssertionError("cross-user switch unexpectedly succeeded")


def test_message_roundtrip_unicode(storage):
    storage["session_repo"].create("user_a", "window_1")
    storage["message_repo"].add_user_message("user_a", "window_1", "你好，杭州")
    storage["message_repo"].add_assistant_message("user_a", "window_1", "收到 🌧️")

    records = storage["message_repo"].list_messages("user_a", "window_1")

    assert [record.content for record in records] == ["你好，杭州", "收到 🌧️"]


def test_tool_calls_roundtrip(storage):
    storage["session_repo"].create("user_a", "window_1")
    call = ToolCall(
        id="call_1",
        name="weather",
        arguments={"city": "北京"},
        raw_arguments='{"city":"北京"}',
    )
    storage["message_repo"].add_assistant_tool_calls(
        "user_a",
        "window_1",
        [call],
    )
    storage["message_repo"].add_tool_result(
        "user_a",
        "window_1",
        "call_1",
        json.dumps({"success": True}, ensure_ascii=False),
    )

    records = storage["message_repo"].list_messages("user_a", "window_1")
    api_messages = storage["message_repo"].to_api_messages(records)

    assert api_messages[0]["tool_calls"][0]["function"]["arguments"] == '{"city":"北京"}'
    assert api_messages[1]["role"] == "tool"
    assert api_messages[1]["tool_call_id"] == "call_1"


def test_session_list_sorted_by_updated_at(storage):
    repo = storage["session_repo"]
    repo.create("user_a", "older")
    repo.create("user_a", "newer")
    with storage["database"].connect() as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE user_id = ? AND id = ?",
            ("2026-01-01T00:00:00Z", "user_a", "older"),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE user_id = ? AND id = ?",
            ("2026-02-01T00:00:00Z", "user_a", "newer"),
        )

    assert [item.id for item in repo.list_by_user("user_a")] == ["newer", "older"]


def test_trace_roundtrip(storage):
    storage["session_repo"].create("user_a", "window_1")
    repo = storage["trace_repo"]
    repo.create("trace_1", "user_a", "window_1", "计算 1+1")
    repo.add_step(
        trace_id="trace_1",
        step_number=1,
        event_index=0,
        event_type="context_built",
        status="success",
        input_data={"tokens": 20},
    )
    repo.finish(
        "trace_1",
        status="completed",
        total_steps=1,
        total_prompt_tokens=20,
        total_completion_tokens=5,
    )

    trace = repo.get("trace_1")
    steps = repo.list_steps("trace_1")

    assert trace.status == "completed"
    assert trace.total_prompt_tokens == 20
    assert steps[0].input_data == {"tokens": 20}

