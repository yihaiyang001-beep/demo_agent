from __future__ import annotations

import os
import uuid
from dataclasses import replace

import pytest

from mini_agent.bootstrap import build_application
from mini_agent.config import Config
from mini_agent.domain.models import ToolRuntimeContext
from mini_agent.tools.weather import WeatherArgs, WeatherTool

pytestmark = pytest.mark.live
LIVE_ENABLED = os.getenv("RUN_LIVE_TESTS") == "1"
LLM_LIVE_ENABLED = LIVE_ENABLED and bool(os.getenv("AGENT_API_KEY"))


def _live_application(tmp_path):
    config = replace(
        Config.from_env(),
        db_path=str(tmp_path / "live-agent.db"),
        max_steps=8,
    )
    return build_application(config)


def _trace_tool_names(application, trace_id):
    return [
        step.name
        for step in application.trace_repo.list_steps(trace_id)
        if step.event_type == "tool_result"
    ]


@pytest.mark.skipif(not LIVE_ENABLED, reason="set RUN_LIVE_TESTS=1")
def test_live_open_meteo_weather():
    config = Config(api_key="weather-live-only", db_path=":memory:")
    result = WeatherTool(config).execute(
        WeatherArgs(city="江西省宜春市", date="today"),
        ToolRuntimeContext(
            user_id="live_user",
            session_id="weather",
            trace_id="weather_live",
        ),
    )

    assert result["source"] == "Open-Meteo"
    assert result["city"] == "宜春市"
    assert result["region"] == "江西"
    assert result["weather_scope"] == "daily_most_severe_forecast"
    assert result["date"]


@pytest.mark.skipif(
    not LLM_LIVE_ENABLED,
    reason="set RUN_LIVE_TESTS=1 and AGENT_API_KEY",
)
def test_live_calculator_loop(tmp_path):
    application = _live_application(tmp_path)
    result = application.runtime.run(
        "live_user",
        f"calculator_{uuid.uuid4().hex[:8]}",
        "请使用计算器计算 123 * 456，并只报告结果。",
    )

    assert result.status == "completed"
    assert "calculator" in _trace_tool_names(application, result.trace_id)
    assert "56088" in result.answer


@pytest.mark.skipif(
    not LLM_LIVE_ENABLED,
    reason="set RUN_LIVE_TESTS=1 and AGENT_API_KEY",
)
def test_live_weather_tool(tmp_path):
    application = _live_application(tmp_path)
    result = application.runtime.run(
        "live_user",
        f"weather_{uuid.uuid4().hex[:8]}",
        "请使用天气工具查询北京今天的天气。",
    )

    assert result.status == "completed"
    assert "weather" in _trace_tool_names(application, result.trace_id)


@pytest.mark.skipif(
    not LLM_LIVE_ENABLED,
    reason="set RUN_LIVE_TESTS=1 and AGENT_API_KEY",
)
def test_live_todo_add_and_list(tmp_path):
    application = _live_application(tmp_path)
    session_id = f"todo_{uuid.uuid4().hex[:8]}"
    added = application.runtime.run(
        "live_user",
        session_id,
        "请添加待办：完成 Agent Runtime live 测试。",
    )
    listed = application.runtime.run(
        "live_user",
        session_id,
        "请使用待办工具列出当前会话的待办。",
    )

    assert added.status == listed.status == "completed"
    assert application.todo_repo.list("live_user", session_id)
    assert "todo" in _trace_tool_names(application, added.trace_id)
    assert "todo" in _trace_tool_names(application, listed.trace_id)


@pytest.mark.skipif(
    not LLM_LIVE_ENABLED,
    reason="set RUN_LIVE_TESTS=1 and AGENT_API_KEY",
)
def test_live_multi_tool_and_follow_up(tmp_path):
    application = _live_application(tmp_path)
    session_id = f"multi_{uuid.uuid4().hex[:8]}"
    first = application.runtime.run(
        "live_user",
        session_id,
        "查询北京明天天气；然后添加待办“根据天气准备出行物品”。",
    )
    follow_up = application.runtime.run(
        "live_user",
        session_id,
        "那上海明天呢？请继续使用天气工具。",
    )

    assert first.status == follow_up.status == "completed"
    assert {"weather", "todo"}.issubset(
        set(_trace_tool_names(application, first.trace_id))
    )
    assert "weather" in _trace_tool_names(application, follow_up.trace_id)
