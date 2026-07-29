from __future__ import annotations

import os

import pytest

from mini_agent.config import Config

AGENT_ENV_NAMES = [
    "AGENT_API_KEY",
    "AGENT_BASE_URL",
    "AGENT_MODEL",
    "AGENT_THINKING_ENABLED",
    "AGENT_MAX_OUTPUT_TOKENS",
    "AGENT_TEMPERATURE",
    "AGENT_LLM_TIMEOUT_SECONDS",
    "AGENT_LLM_MAX_RETRIES",
    "AGENT_MAX_STEPS",
    "AGENT_REPEAT_LIMIT",
    "AGENT_MAX_CONTEXT_TOKENS",
    "AGENT_SUMMARY_THRESHOLD_RATIO",
    "AGENT_COLLAPSE_THRESHOLD_RATIO",
    "AGENT_RECENT_MESSAGES",
    "AGENT_COLLAPSE_RECENT_MESSAGES",
    "AGENT_DB_PATH",
    "AGENT_WEATHER_TIMEOUT_SECONDS",
]


@pytest.fixture(autouse=True)
def clear_agent_environment(monkeypatch):
    for name in AGENT_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_config_reads_agent_env(monkeypatch, tmp_path):
    db_path = tmp_path / "nested" / "agent.db"
    monkeypatch.setenv("AGENT_API_KEY", "test-secret")
    monkeypatch.setenv("AGENT_MODEL", "deepseek-test")
    monkeypatch.setenv("AGENT_THINKING_ENABLED", "true")
    monkeypatch.setenv("AGENT_MAX_STEPS", "4")
    monkeypatch.setenv("AGENT_DB_PATH", str(db_path))
    monkeypatch.setenv("CORECODER_MODEL", "must-be-ignored")
    monkeypatch.setenv("OPENAI_API_KEY", "must-also-be-ignored")

    config = Config.from_env()

    assert config.api_key == "test-secret"
    assert config.model == "deepseek-test"
    assert config.thinking_enabled is True
    assert config.max_steps == 4
    assert config.db_path == str(db_path)
    assert db_path.parent.is_dir()
    assert "api_key" not in config.safe_summary()
    assert config.safe_summary()["api_key_configured"] is True


def test_config_rejects_empty_api_key():
    with pytest.raises(ValueError, match="AGENT_API_KEY"):
        Config.from_env()


@pytest.mark.parametrize(
    ("summary_ratio", "collapse_ratio"),
    [("0", "0.9"), ("0.9", "0.9"), ("0.95", "0.90"), ("0.7", "1")],
)
def test_config_rejects_invalid_thresholds(
    monkeypatch, tmp_path, summary_ratio, collapse_ratio
):
    monkeypatch.setenv("AGENT_API_KEY", "test-secret")
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "agent.db"))
    monkeypatch.setenv("AGENT_SUMMARY_THRESHOLD_RATIO", summary_ratio)
    monkeypatch.setenv("AGENT_COLLAPSE_THRESHOLD_RATIO", collapse_ratio)

    with pytest.raises(ValueError, match="context ratios"):
        Config.from_env()


def test_config_does_not_read_legacy_environment(monkeypatch):
    monkeypatch.setenv("CORECODER_API_KEY", "legacy-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")

    with pytest.raises(ValueError, match="AGENT_API_KEY"):
        Config.from_env()

    assert os.getenv("CORECODER_API_KEY") == "legacy-secret"

