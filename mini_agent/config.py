"""Validated configuration loaded exclusively from ``AGENT_*`` variables."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    thinking_enabled: bool = False
    max_output_tokens: int = 4096
    temperature: float = 0.0
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 3
    max_steps: int = 8
    repeat_limit: int = 2
    max_context_tokens: int = 32_000
    summary_threshold_ratio: float = 0.70
    collapse_threshold_ratio: float = 0.90
    recent_messages: int = 12
    collapse_recent_messages: int = 6
    db_path: str = "./data/agent.db"
    weather_timeout_seconds: int = 8

    @classmethod
    def from_env(cls) -> Config:
        """Load ``.env`` and then read only the namespaced ``AGENT_*`` settings."""
        load_dotenv(override=False)
        config = cls(
            api_key=os.getenv("AGENT_API_KEY", "").strip(),
            base_url=os.getenv("AGENT_BASE_URL", "https://api.deepseek.com").strip(),
            model=os.getenv("AGENT_MODEL", "deepseek-v4-pro").strip(),
            thinking_enabled=_read_bool("AGENT_THINKING_ENABLED", False),
            max_output_tokens=_read_int("AGENT_MAX_OUTPUT_TOKENS", 4096),
            temperature=_read_float("AGENT_TEMPERATURE", 0.0),
            llm_timeout_seconds=_read_int("AGENT_LLM_TIMEOUT_SECONDS", 30),
            llm_max_retries=_read_int("AGENT_LLM_MAX_RETRIES", 3),
            max_steps=_read_int("AGENT_MAX_STEPS", 8),
            repeat_limit=_read_int("AGENT_REPEAT_LIMIT", 2),
            max_context_tokens=_read_int("AGENT_MAX_CONTEXT_TOKENS", 32_000),
            summary_threshold_ratio=_read_float("AGENT_SUMMARY_THRESHOLD_RATIO", 0.70),
            collapse_threshold_ratio=_read_float("AGENT_COLLAPSE_THRESHOLD_RATIO", 0.90),
            recent_messages=_read_int("AGENT_RECENT_MESSAGES", 12),
            collapse_recent_messages=_read_int("AGENT_COLLAPSE_RECENT_MESSAGES", 6),
            db_path=os.getenv("AGENT_DB_PATH", "./data/agent.db").strip(),
            weather_timeout_seconds=_read_int("AGENT_WEATHER_TIMEOUT_SECONDS", 8),
        )
        config.validate()
        config.ensure_storage_directory()
        return config

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError("AGENT_API_KEY must not be empty")
        if not self.base_url:
            raise ValueError("AGENT_BASE_URL must not be empty")
        if not self.model:
            raise ValueError("AGENT_MODEL must not be empty")
        if self.max_output_tokens < 1:
            raise ValueError("AGENT_MAX_OUTPUT_TOKENS must be at least 1")
        if self.llm_timeout_seconds < 1:
            raise ValueError("AGENT_LLM_TIMEOUT_SECONDS must be at least 1")
        if self.llm_max_retries < 1:
            raise ValueError("AGENT_LLM_MAX_RETRIES must be at least 1")
        if self.max_steps < 1:
            raise ValueError("AGENT_MAX_STEPS must be at least 1")
        if self.repeat_limit < 1:
            raise ValueError("AGENT_REPEAT_LIMIT must be at least 1")
        if self.max_context_tokens < 1:
            raise ValueError("AGENT_MAX_CONTEXT_TOKENS must be at least 1")
        if not (
            0 < self.summary_threshold_ratio < self.collapse_threshold_ratio < 1
        ):
            raise ValueError(
                "context ratios must satisfy "
                "0 < AGENT_SUMMARY_THRESHOLD_RATIO < "
                "AGENT_COLLAPSE_THRESHOLD_RATIO < 1"
            )
        if self.recent_messages < 1 or self.collapse_recent_messages < 1:
            raise ValueError("recent message windows must be at least 1")
        if self.collapse_recent_messages > self.recent_messages:
            raise ValueError(
                "AGENT_COLLAPSE_RECENT_MESSAGES must not exceed AGENT_RECENT_MESSAGES"
            )
        if not self.db_path:
            raise ValueError("AGENT_DB_PATH must not be empty")
        if self.weather_timeout_seconds < 1:
            raise ValueError("AGENT_WEATHER_TIMEOUT_SECONDS must be at least 1")

    def ensure_storage_directory(self) -> None:
        if self.db_path == ":memory:":
            return
        Path(self.db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    def safe_summary(self) -> dict[str, Any]:
        """Return non-sensitive startup information."""
        values = asdict(self)
        values.pop("api_key", None)
        values["api_key_configured"] = bool(self.api_key)
        return values

