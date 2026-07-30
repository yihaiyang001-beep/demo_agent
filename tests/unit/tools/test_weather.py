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
                "admin1": "北京市",
                "admin2": "北京市",
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
    assert requests[0].url.params["count"] == "10"
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
        "region": "北京市",
        "country": "中国",
        "latitude": 39.9042,
        "longitude": 116.4074,
        "date": "2026-07-30",
        "weather": "阵雨",
        "weather_code": 80,
        "weather_scope": "daily_most_severe_forecast",
        "weather_note": "全天最严重天气预报，不代表全天持续或现场实况",
        "temperature_min_c": 24.1,
        "temperature_max_c": 31.5,
        "precipitation_probability_max": 65,
        "data_type": "numerical_weather_prediction",
        "source": "Open-Meteo",
    }


def test_weather_retries_full_chinese_city_with_pinyin_and_disambiguates(
    runtime_context,
):
    requests = []
    yichun_results = {
        "results": [
            {
                "name": "伊春",
                "country": "中国",
                "admin1": "黑龙江",
                "admin2": "伊春市",
                "latitude": 47.72143,
                "longitude": 128.87529,
                "timezone": "Asia/Shanghai",
            },
            {
                "name": "宜春明月山机场",
                "country": "中国",
                "admin1": "江西",
                "admin2": "宜春市",
                "feature_code": "AIRP",
                "latitude": 27.80347,
                "longitude": 114.3082,
                "timezone": "Asia/Shanghai",
            },
            {
                "name": "Yichun",
                "country": "中国",
                "admin1": "江西",
                "admin2": "宜春市",
                "feature_code": "PPLA2",
                "population": 1045952,
                "latitude": 27.83333,
                "longitude": 114.4,
                "timezone": "Asia/Shanghai",
            },
        ]
    }

    def handler(request):
        requests.append(request)
        if "geocoding-api" not in request.url.host:
            return httpx.Response(200, json=forecast_payload())
        if request.url.params["name"] == "yichun":
            return httpx.Response(200, json=yichun_results)
        return httpx.Response(200, json={"generationtime_ms": 0.1})

    result = make_tool(handler).execute(
        WeatherArgs(city="江西省宜春市", date="tomorrow"),
        runtime_context,
    )

    geocoding_queries = [
        request.url.params["name"]
        for request in requests
        if "geocoding-api" in request.url.host
    ]
    assert geocoding_queries == ["江西省宜春市", "宜春", "yichun"]
    assert result["city"] == "宜春市"
    assert result["region"] == "江西"
    assert result["latitude"] == 27.83333
    assert result["longitude"] == 114.4


def test_weather_city_not_found(runtime_context):
    tool = make_tool(lambda _request: httpx.Response(200, json={"results": []}))

    with pytest.raises(ToolExecutionError) as exc_info:
        tool.execute(WeatherArgs(city="不存在"), runtime_context)

    assert exc_info.value.code == "CITY_NOT_FOUND"


def test_weather_missing_results_means_city_not_found(runtime_context):
    tool = make_tool(
        lambda _request: httpx.Response(
            200,
            json={"generationtime_ms": 0.1},
        )
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        tool.execute(WeatherArgs(city="宜春"), runtime_context)

    assert exc_info.value.code == "CITY_NOT_FOUND"


def test_weather_invalid_geocoding_results(runtime_context):
    tool = make_tool(
        lambda _request: httpx.Response(
            200,
            json={"results": {"name": "北京"}},
        )
    )

    with pytest.raises(ToolExecutionError) as exc_info:
        tool.execute(WeatherArgs(city="北京"), runtime_context)

    assert exc_info.value.code == "WEATHER_RESPONSE_INVALID"


def test_weather_timeout(runtime_context):
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    tool = make_tool(handler)

    with pytest.raises(ToolExecutionError) as exc_info:
        tool.execute(WeatherArgs(city="北京"), runtime_context)

    assert exc_info.value.code == "WEATHER_TIMEOUT"


def test_weather_network_error(runtime_context):
    def handler(request):
        raise httpx.ConnectError("connection failed", request=request)

    tool = make_tool(handler)

    with pytest.raises(ToolExecutionError) as exc_info:
        tool.execute(WeatherArgs(city="北京"), runtime_context)

    assert exc_info.value.code == "WEATHER_NETWORK_ERROR"


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
