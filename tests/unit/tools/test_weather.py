from __future__ import annotations

from datetime import date

import httpx
import pytest

from mini_agent.config import Config
from mini_agent.domain.errors import ToolExecutionError
from mini_agent.tools.weather import WeatherArgs, WeatherTool


def make_config():
    return Config(api_key="weather-test", db_path=":memory:")


def geocoding_payload():
    return {
        "results": [
            {
                "name": "北京市",
                "country": "中国",
                "latitude": 39.9042,
                "longitude": 116.4074,
                "timezone": "Asia/Shanghai",
            }
        ]
    }


def forecast_payload():
    return {
        "daily": {
            "time": ["2026-07-30"],
            "weather_code": [80],
            "temperature_2m_max": [31.5],
            "temperature_2m_min": [24.1],
            "precipitation_probability_max": [65],
        }
    }


def make_tool(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return WeatherTool(
        make_config(),
        http_client=client,
        today_provider=lambda _timezone: date(2026, 7, 29),
    )


def test_weather_geocodes_city(runtime_context):
    requests = []

    def handler(request):
        requests.append(request)
        if "geocoding-api" in request.url.host:
            return httpx.Response(200, json=geocoding_payload())
        return httpx.Response(200, json=forecast_payload())

    result = make_tool(handler).execute(
        WeatherArgs(city="北京", date="tomorrow"),
        runtime_context,
    )

    assert requests[0].url.params["name"] == "北京"
    assert requests[0].url.params["language"] == "zh"
    assert requests[1].url.params["latitude"] == "39.9042"
    assert result["city"] == "北京市"


def test_weather_returns_compact_result(runtime_context):
    def handler(request):
        payload = geocoding_payload() if "geocoding-api" in request.url.host else forecast_payload()
        return httpx.Response(200, json=payload)

    result = make_tool(handler).execute(
        WeatherArgs(city="北京", date="tomorrow"),
        runtime_context,
    )

    assert result == {
        "city": "北京市",
        "country": "中国",
        "date": "2026-07-30",
        "weather": "阵雨",
        "weather_code": 80,
        "temperature_min_c": 24.1,
        "temperature_max_c": 31.5,
        "precipitation_probability_max": 65,
        "source": "Open-Meteo",
    }


def test_weather_city_not_found(runtime_context):
    tool = make_tool(lambda _request: httpx.Response(200, json={"results": []}))

    with pytest.raises(ToolExecutionError) as exc_info:
        tool.execute(WeatherArgs(city="不存在"), runtime_context)

    assert exc_info.value.code == "CITY_NOT_FOUND"


def test_weather_timeout(runtime_context):
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    tool = make_tool(handler)

    with pytest.raises(ToolExecutionError) as exc_info:
        tool.execute(WeatherArgs(city="北京"), runtime_context)

    assert exc_info.value.code == "WEATHER_TIMEOUT"


@pytest.mark.parametrize("raw_date", ["next week", "2026-07-28", "2026-08-20"])
def test_weather_invalid_date(runtime_context, raw_date):
    def handler(request):
        if "geocoding-api" in request.url.host:
            return httpx.Response(200, json=geocoding_payload())
        raise AssertionError("forecast must not be requested for an invalid date")

    tool = make_tool(handler)

    with pytest.raises(ToolExecutionError) as exc_info:
        tool.execute(WeatherArgs(city="北京", date=raw_date), runtime_context)

    assert exc_info.value.code == "INVALID_WEATHER_DATE"


def test_weather_response_invalid(runtime_context):
    def handler(request):
        if "geocoding-api" in request.url.host:
            return httpx.Response(200, json=geocoding_payload())
        return httpx.Response(200, json={"daily": {"time": []}})

    tool = make_tool(handler)

    with pytest.raises(ToolExecutionError) as exc_info:
        tool.execute(
            WeatherArgs(city="北京", date="tomorrow"),
            runtime_context,
        )

    assert exc_info.value.code == "WEATHER_RESPONSE_INVALID"

