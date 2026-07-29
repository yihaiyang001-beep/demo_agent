from __future__ import annotations

from mini_agent.bootstrap import build_application
from mini_agent.cli import run_cli
from mini_agent.config import Config
from mini_agent.domain.models import LLMResponse
from tests.fakes.scripted_llm import ScriptedLLM


def test_cli_creates_lists_and_switches_sessions(tmp_path):
    application = build_application(
        Config(api_key="cli-test", db_path=str(tmp_path / "agent.db")),
        llm_client=ScriptedLLM(
            [
                LLMResponse(content="window one reply"),
                LLMResponse(content="window two reply"),
            ]
        ),
    )
    commands = iter(
        [
            "hello window one",
            "/new window_2",
            "hello window two",
            "/sessions",
            "/switch window_1",
            "/current",
            "/exit",
        ]
    )
    output = []

    run_cli(
        application,
        user_id="user_a",
        session_id="window_1",
        input_fn=lambda _prompt: next(commands),
        output_fn=output.append,
    )

    joined = "\n".join(output)
    assert "window_1" in joined
    assert "window_2" in joined
    assert application.message_repo.list_messages("user_a", "window_1")[0].content == (
        "hello window one"
    )
    assert application.message_repo.list_messages("user_a", "window_2")[0].content == (
        "hello window two"
    )


def test_cli_trace_command_displays_latest_trace(tmp_path):
    application = build_application(
        Config(api_key="cli-test", db_path=str(tmp_path / "agent.db")),
        llm_client=ScriptedLLM([LLMResponse(content="done")]),
    )
    commands = iter(["hello", "/trace", "/exit"])
    output = []

    run_cli(
        application,
        user_id="user_a",
        session_id="window_1",
        input_fn=lambda _prompt: next(commands),
        output_fn=output.append,
    )

    joined = "\n".join(output)
    assert "Status: completed" in joined
    assert "llm_decision" in joined
    assert "Tokens:" in joined
