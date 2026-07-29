from __future__ import annotations

from mini_agent.domain.models import ToolCall
from mini_agent.runtime.repetition_guard import RepetitionGuard, tool_call_fingerprint


def call(city="北京"):
    return ToolCall(
        id="call_1",
        name="weather",
        arguments={"date": "today", "city": city},
        raw_arguments="",
    )


def test_fingerprint_sorts_arguments():
    first = call()
    second = ToolCall(
        id="call_2",
        name="weather",
        arguments={"city": "北京", "date": "today"},
        raw_arguments="",
    )
    assert tool_call_fingerprint(first) == tool_call_fingerprint(second)


def test_third_consecutive_call_is_blocked():
    guard = RepetitionGuard(limit=2)
    assert guard.should_block(call()) is False
    assert guard.should_block(call()) is False
    assert guard.should_block(call()) is True


def test_different_call_resets_count():
    guard = RepetitionGuard(limit=2)
    guard.should_block(call())
    guard.should_block(call())
    assert guard.should_block(call("上海")) is False
    assert guard.should_block(call()) is False

