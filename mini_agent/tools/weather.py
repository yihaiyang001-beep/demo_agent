"""Compact Open-Meteo weather lookup."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import Field
from pypinyin import Style, lazy_pinyin

from mini_agent.config import Config
from mini_agent.domain.errors import ToolExecutionError
from mini_agent.domain.models import ToolRuntimeContext

from .base import BaseTool, ToolArgs

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

HAN_CHARACTER_RE = re.compile(r"[\u3400-\u9fff]")
ADMINISTRATIVE_DIVIDER_RE = re.compile(
    r"(?:特别行政区|维吾尔自治区|壮族自治区|回族自治区|自治区|自治州|"
    r"省|市|地区|盟|县|区)"
)

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
    description = (
        "Get a compact daily Open-Meteo forecast. The weather field is the most "
        "severe condition forecast for the whole day, not an observed current condition."
    )
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
        place = self._geocode_city(args.city)
        try:
            latitude = float(place["latitude"])
            longitude = float(place["longitude"])
            city = self._display_city_name(place, args.city)
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
            "region": str(place.get("admin1") or ""),
            "country": str(place.get("country") or ""),
            "latitude": latitude,
            "longitude": longitude,
            "date": target_date.isoformat(),
            "weather": WEATHER_CODES.get(weather_code, "未知天气"),
            "weather_code": weather_code,
            "weather_scope": "daily_most_severe_forecast",
            "weather_note": "全天最严重天气预报，不代表全天持续或现场实况",
            "temperature_min_c": temperature_min,
            "temperature_max_c": temperature_max,
            "precipitation_probability_max": precipitation,
            "data_type": "numerical_weather_prediction",
            "source": "Open-Meteo",
        }

    def _geocode_city(self, requested_city: str) -> dict[str, Any]:
        for query in self._geocoding_queries(requested_city):
            geocoding = self._request_json(
                GEOCODING_URL,
                params={
                    "name": query,
                    "count": 10,
                    "language": "zh",
                    "format": "json",
                },
            )
            if "results" not in geocoding:
                # Open-Meteo returns HTTP 200 without a results field for some
                # valid searches that have no match, including some Chinese names.
                continue

            results = geocoding["results"]
            if not isinstance(results, list):
                raise ToolExecutionError(
                    "WEATHER_RESPONSE_INVALID",
                    "天气地理编码响应格式无效",
                )
            if not results:
                continue

            places = [item for item in results if isinstance(item, dict)]
            if not places:
                raise ToolExecutionError(
                    "WEATHER_RESPONSE_INVALID",
                    "天气地理编码响应缺少有效地点",
                )
            return self._select_place(places, requested_city)

        raise ToolExecutionError(
            "CITY_NOT_FOUND",
            f"未找到城市：{requested_city}",
        )

    @classmethod
    def _geocoding_queries(cls, requested_city: str) -> list[str]:
        original = requested_city.strip()
        locality = cls._locality_component(original)
        candidates = [original]
        if locality and locality != original:
            candidates.append(locality)
        if HAN_CHARACTER_RE.search(locality):
            pinyin = "".join(
                lazy_pinyin(locality, style=Style.NORMAL, errors="ignore")
            )
            if pinyin:
                candidates.append(pinyin)

        queries: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.casefold()
            if candidate and key not in seen:
                seen.add(key)
                queries.append(candidate)
        return queries

    @staticmethod
    def _locality_component(requested_city: str) -> str:
        parts = [
            part.strip()
            for part in ADMINISTRATIVE_DIVIDER_RE.split(requested_city)
            if part.strip()
        ]
        return parts[-1] if parts else requested_city.strip()

    @classmethod
    def _select_place(
        cls,
        places: list[dict[str, Any]],
        requested_city: str,
    ) -> dict[str, Any]:
        requested = cls._normalize_location_text(requested_city)
        tokens = {
            cls._normalize_location_text(token)
            for token in ADMINISTRATIVE_DIVIDER_RE.split(requested_city)
            if cls._normalize_location_text(token)
        }
        locality = cls._normalize_location_text(
            cls._locality_component(requested_city)
        )
        if locality:
            tokens.add(locality)

        def score(place: dict[str, Any]) -> tuple[int, int, int]:
            value = 0
            for field in ("name", "admin1", "admin2", "admin3", "admin4"):
                raw_field = str(place.get(field) or "")
                normalized_field = cls._normalize_location_text(raw_field)
                normalized_base = cls._normalize_location_text(
                    cls._locality_component(raw_field)
                )
                if requested and normalized_field == requested:
                    value += 200
                for token in tokens:
                    if token == normalized_field:
                        value += 100
                    elif token == normalized_base:
                        value += 90
            feature_code = str(place.get("feature_code") or "")
            feature_rank = {
                "PPLC": 70,
                "PPLA": 60,
                "PPLA2": 50,
                "PPLA3": 40,
                "PPLA4": 30,
                "PPL": 20,
                "PPLX": 10,
            }.get(feature_code, 0)
            try:
                population = int(place.get("population") or 0)
            except (TypeError, ValueError):
                population = 0
            return value, feature_rank, population

        return max(places, key=score)

    @classmethod
    def _display_city_name(
        cls,
        place: dict[str, Any],
        requested_city: str,
    ) -> str:
        locality = cls._normalize_location_text(
            cls._locality_component(requested_city)
        )
        for field in ("name", "admin2", "admin3", "admin1"):
            value = str(place.get(field) or "")
            normalized = cls._normalize_location_text(
                cls._locality_component(value)
            )
            if locality and normalized == locality:
                return value
        return str(place["name"])

    @staticmethod
    def _normalize_location_text(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

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
