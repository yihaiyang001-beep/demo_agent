from __future__ import annotations

import json
from typing import Any

from mini_agent.bootstrap import build_application
from mini_agent.config import Config
from mini_agent.domain.models import LLMResponse, ToolCall, ToolRuntimeContext
from mini_agent.tools.base import BaseTool, ToolArgs
from mini_agent.tools.registry import ToolRegistry
from tests.fakes.scripted_llm import ScriptedLLM


class WeatherArgs(ToolArgs):
    city: str
    date: str = "tomorrow"


class FakeWeatherTool(BaseTool):
    name = "weather"
    description = "Fake weather for context integration tests"
    args_model = WeatherArgs

    def execute(self, args: ToolArgs, context: ToolRuntimeContext) -> dict[str, Any]:
        assert isinstance(args, WeatherArgs)
        return {"city": args.city, "date": args.date, "weather": "晴"}


def test_compressed_tool_follow_up_continues_runtime(tmp_path):
    registry = ToolRegistry()
    registry.register(FakeWeatherTool())
    weather_call = ToolCall(
        id="call_weather",
        name="weather",
        arguments={"city": "上海", "date": "tomorrow"},
        raw_arguments='{"city":"上海","date":"tomorrow"}',
    )
    llm = ScriptedLLM(
        [
            LLMResponse(content="早期话题：用户在比较北京和上海天气。"),
            LLMResponse(content="", tool_calls=[weather_call]),
            LLMResponse(content="更新话题：用户正在查询上海明天天气。"),
            LLMResponse(content="上海明天晴。"),
        ]
    )
    application = build_application(
        Config(
            api_key="context-integration",
            db_path=str(tmp_path / "agent.db"),
            max_context_tokens=500,
            summary_threshold_ratio=0.7,
            collapse_threshold_ratio=0.9,
            recent_messages=4,
            collapse_recent_messages=2,
        ),
        llm_client=llm,
        tool_registry=registry,
    )
    application.session_service.create("user_a", "window_1")
    for index in range(4):
        application.message_repo.add_user_message(
            "user_a",
            "window_1",
            ("查北京天气" if index == 0 else f"填充对话 {index}") + "x" * 70,
        )
        application.message_repo.add_assistant_message(
            "user_a",
            "window_1",
            f"历史回复 {index}" + "y" * 70,
        )

    result = application.runtime.run("user_a", "window_1", "那上海呢？")

    assert result.status == "completed"
    assert result.answer == "上海明天晴。"
    assert "[SESSION SUMMARY]" in llm.requests[1]["messages"][0]["content"]
    assert application.summary_repo.get("user_a", "window_1") is not None
    tool_payload = json.loads(llm.requests[3]["messages"][-1]["content"])
    assert tool_payload["data"]["city"] == "上海"
