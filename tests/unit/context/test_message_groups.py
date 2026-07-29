from __future__ import annotations

from mini_agent.context.message_groups import group_messages, split_recent_groups
from mini_agent.domain.models import MessageRecord


def record(message_id, role, *, tool_call_id=None, tool_calls=None):
    return MessageRecord(
        id=message_id,
        user_id="user_a",
        session_id="window_1",
        role=role,
        content=role,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        created_at="2026-01-01T00:00:00Z",
    )


def test_tool_call_group_is_never_split():
    records = [
        record(1, "user"),
        record(2, "assistant"),
        record(3, "user"),
        record(
            4,
            "assistant",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "weather", "arguments": "{}"},
                }
            ],
        ),
        record(5, "tool", tool_call_id="call_1"),
        record(6, "assistant"),
    ]

    older, recent = split_recent_groups(group_messages(records), target_messages=2)

    assert [item.id for item in older[0].messages] == [1, 2]
    assert [item.id for item in recent[0].messages] == [3, 4, 5, 6]

