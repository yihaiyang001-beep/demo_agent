"""Compact Open-Meteo weather lookup."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import Field

from mini_agent.config import Config
from mini_agent.domain.errors import ToolExecutionError
from mini_agent.domain.models import ToolRuntimeContext

from .base import BaseTool, ToolArgs

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    56: "轻微冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻微冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴强冰雹",
}


class WeatherArgs(ToolArgs):
    city: str = Field(min_length=1, max_length=80)
    date: str = Field(default="today", description="today、tomorrow 或 YYYY-MM-DD")


class WeatherTool(BaseTool):
    name = "weather"
    description = "Get a compact daily weather forecast from Open-Meteo."
    args_model = WeatherArgs

    def __init__(
        self,
        config: Config,
        *,
        http_client: httpx.Client | None = None,
        today_provider: Callable[[ZoneInfo], date] | None = None,
    ):
        self.http_client = http_client or httpx.Client(
            timeout=config.weather_timeout_seconds
        )
        self._today_provider = today_provider or (
            lambda timezone: datetime.now(timezone).date()
        )

    def execute(self, args: ToolArgs, context: ToolRuntimeContext) -> dict[str, Any]:
        assert isinstance(args, WeatherArgs)
        geocoding = self._request_json(
            GEOCODING_URL,
            params={
                "name": args.city,
                "count": 1,
                "language": "zh",
                "format": "json",
            },
        )
        results = geocoding.get("results")
        if not isinstance(results, list):
            raise ToolExecutionError(
                "WEATHER_RESPONSE_INVALID",
                "天气地理编码响应格式无效",
            )
        if not results:
            raise ToolExecutionError(
                "CITY_NOT_FOUND",
                f"未找到城市：{args.city}",
            )

        place = results[0]
        try:
            latitude = float(place["latitude"])
            longitude = float(place["longitude"])
            city = str(place["name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ToolExecutionError(
                "WEATHER_RESPONSE_INVALID",
                "天气地理编码响应缺少必要字段",
                str(exc),
            ) from exc

        timezone_name = str(place.get("timezone") or "UTC")
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            timezone = ZoneInfo("UTC")
        local_today = self._today_provider(timezone)
        target_date = self._resolve_date(args.date, local_today)

        forecast = self._request_json(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max"
                ),
                "timezone": "auto",
                "start_date": target_date.isoformat(),
                "end_date": target_date.isoformat(),
            },
        )
        daily = forecast.get("daily")
        if not isinstance(daily, dict):
            raise ToolExecutionError(
                "WEATHER_RESPONSE_INVALID",
                "天气预报响应格式无效",
            )

        try:
            index = daily["time"].index(target_date.isoformat())
            weather_code = int(daily["weather_code"][index])
            temperature_max = float(daily["temperature_2m_max"][index])
            temperature_min = float(daily["temperature_2m_min"][index])
            precipitation = int(daily["precipitation_probability_max"][index])
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
            raise ToolExecutionError(
                "WEATHER_RESPONSE_INVALID",
                "天气预报响应缺少指定日期的数据",
                str(exc),
            ) from exc

        return {
            "city": city,
            "country": str(place.get("country") or ""),
            "date": target_date.isoformat(),
            "weather": WEATHER_CODES.get(weather_code, "未知天气"),
            "weather_code": weather_code,
            "temperature_min_c": temperature_min,
            "temperature_max_c": temperature_max,
            "precipitation_probability_max": precipitation,
            "source": "Open-Meteo",
        }

    @staticmethod
    def _resolve_date(raw: str, local_today: date) -> date:
        normalized = raw.strip().lower()
        if normalized == "today":
            return local_today
        if normalized == "tomorrow":
            return local_today + timedelta(days=1)
        try:
            target = date.fromisoformat(normalized)
        except ValueError as exc:
            raise ToolExecutionError(
                "INVALID_WEATHER_DATE",
                "天气日期必须是 today、tomorrow 或 YYYY-MM-DD",
            ) from exc
        if target < local_today or target > local_today + timedelta(days=16):
            raise ToolExecutionError(
                "INVALID_WEATHER_DATE",
                "天气日期必须在今天起 16 天预报范围内",
            )
        return target

    def _request_json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.http_client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ToolExecutionError(
                "WEATHER_TIMEOUT",
                "天气服务请求超时",
                str(exc),
            ) from exc
        except httpx.RequestError as exc:
            raise ToolExecutionError(
                "WEATHER_NETWORK_ERROR",
                "天气服务网络连接失败",
                str(exc),
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ToolExecutionError(
                "WEATHER_NETWORK_ERROR",
                f"天气服务返回 HTTP {exc.response.status_code}",
                str(exc),
            ) from exc
        except ValueError as exc:
            raise ToolExecutionError(
                "WEATHER_RESPONSE_INVALID",
                "天气服务返回了无效 JSON",
                str(exc),
            ) from exc

        if not isinstance(payload, dict):
            raise ToolExecutionError(
                "WEATHER_RESPONSE_INVALID",
                "天气服务响应必须是 JSON 对象",
            )
        return payload

