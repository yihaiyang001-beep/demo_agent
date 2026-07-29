from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APITimeoutError, BadRequestError

from mini_agent.config import Config
from mini_agent.domain.errors import LLMBadRequestError
from mini_agent.llm.deepseek_client import DeepSeekClient


def make_config(**overrides) -> Config:
    values = {
        "api_key": "unit-test-secret",
        "base_url": "https://example.invalid",
        "model": "deepseek-v4-pro",
        "thinking_enabled": False,
        "max_output_tokens": 512,
        "temperature": 0.0,
        "llm_timeout_seconds": 5,
        "llm_max_retries": 3,
        "max_steps": 8,
        "repeat_limit": 2,
        "max_context_tokens": 32000,
        "summary_threshold_ratio": 0.7,
        "collapse_threshold_ratio": 0.9,
        "recent_messages": 12,
        "collapse_recent_messages": 6,
        "db_path": ":memory:",
        "weather_timeout_seconds": 8,
    }
    values.update(overrides)
    return Config(**values)


def make_tool_call(
    *,
    call_id: str = "call_1",
    name: str = "calculator",
    arguments: str = '{"expression":"1 + 1"}',
):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def make_response(*, content="hello", tool_calls=None, prompt_tokens=11, completion_tokens=7):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=message,
                finish_reason="tool_calls" if tool_calls else "stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )


def make_sdk_client(response):
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def test_non_stream_request_parameters():
    sdk_client = make_sdk_client(make_response())
    client = DeepSeekClient(make_config(), client=sdk_client)
    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "function": {"name": "calculator"}}]

    client.chat(messages, tools)

    kwargs = sdk_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["messages"] == messages
    assert kwargs["stream"] is False
    assert kwargs["max_tokens"] == 512
    assert kwargs["temperature"] == 0
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == "auto"


def test_thinking_is_explicitly_disabled():
    sdk_client = make_sdk_client(make_response())
    client = DeepSeekClient(make_config(thinking_enabled=False), client=sdk_client)

    client.chat([{"role": "user", "content": "hello"}])

    kwargs = sdk_client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs


def test_parse_direct_answer():
    sdk_client = make_sdk_client(
        make_response(content="完整回答", prompt_tokens=13, completion_tokens=5)
    )
    client = DeepSeekClient(make_config(), client=sdk_client)

    response = client.chat([{"role": "user", "content": "你好"}])

    assert response.content == "完整回答"
    assert response.tool_calls == []
    assert response.prompt_tokens == 13
    assert response.completion_tokens == 5
    assert response.finish_reason == "stop"


def test_parse_single_tool_call():
    sdk_client = make_sdk_client(make_response(content=None, tool_calls=[make_tool_call()]))
    client = DeepSeekClient(make_config(), client=sdk_client)

    response = client.chat([{"role": "user", "content": "calculate"}])

    call = response.tool_calls[0]
    assert response.content == ""
    assert call.id == "call_1"
    assert call.name == "calculator"
    assert call.arguments == {"expression": "1 + 1"}
    assert call.raw_arguments == '{"expression":"1 + 1"}'
    assert call.parse_error is None


def test_parse_multiple_tool_calls():
    raw_calls = [
        make_tool_call(call_id="call_1", name="calculator"),
        make_tool_call(
            call_id="call_2",
            name="search",
            arguments='{"query":"agent runtime"}',
        ),
    ]
    sdk_client = make_sdk_client(make_response(content=None, tool_calls=raw_calls))
    client = DeepSeekClient(make_config(), client=sdk_client)

    response = client.chat([{"role": "user", "content": "do both"}])

    assert [call.name for call in response.tool_calls] == ["calculator", "search"]
    assert response.tool_calls[1].arguments == {"query": "agent runtime"}


@pytest.mark.parametrize("arguments", ['{"broken"', "[]", '"text"'])
def test_malformed_tool_arguments_preserve_parse_error(arguments):
    sdk_client = make_sdk_client(
        make_response(content=None, tool_calls=[make_tool_call(arguments=arguments)])
    )
    client = DeepSeekClient(make_config(), client=sdk_client)

    response = client.chat([{"role": "user", "content": "calculate"}])

    call = response.tool_calls[0]
    assert call.arguments is None
    assert call.raw_arguments == arguments
    assert call.parse_error


def test_empty_content_is_preserved_for_tool_call():
    sdk_client = make_sdk_client(make_response(content=None, tool_calls=[make_tool_call()]))
    client = DeepSeekClient(make_config(), client=sdk_client)

    response = client.chat([{"role": "user", "content": "calculate"}])

    assert response.content == ""
    assert len(response.tool_calls) == 1


def test_retry_on_timeout():
    request = httpx.Request("POST", "https://example.invalid/chat/completions")
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.side_effect = [
        APITimeoutError(request=request),
        make_response(content="recovered"),
    ]
    sleeps = []
    retry_events = []
    client = DeepSeekClient(
        make_config(),
        client=sdk_client,
        sleep=sleeps.append,
        on_retry=lambda attempt, code, duration: retry_events.append(
            (attempt, code, duration)
        ),
    )

    response = client.chat([{"role": "user", "content": "hello"}])

    assert response.content == "recovered"
    assert sdk_client.chat.completions.create.call_count == 2
    assert sleeps == [1]
    assert retry_events == [(1, "APITimeoutError", 1000)]


def test_no_retry_on_bad_request():
    request = httpx.Request("POST", "https://example.invalid/chat/completions")
    sdk_response = httpx.Response(400, request=request)
    sdk_client = MagicMock()
    sdk_client.chat.completions.create.side_effect = BadRequestError(
        "bad request",
        response=sdk_response,
        body={"error": {"message": "bad request"}},
    )
    sleeps = []
    client = DeepSeekClient(make_config(), client=sdk_client, sleep=sleeps.append)

    with pytest.raises(LLMBadRequestError):
        client.chat([{"role": "user", "content": "hello"}])

    assert sdk_client.chat.completions.create.call_count == 1
    assert sleeps == []

