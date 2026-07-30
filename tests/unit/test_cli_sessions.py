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


def test_cli_manual_compact_command(tmp_path):
    application = build_application(
        Config(api_key="cli-test", db_path=str(tmp_path / "agent.db")),
        llm_client=ScriptedLLM(
            [
                LLMResponse(content="first reply"),
                LLMResponse(content="second reply"),
                LLMResponse(content="manual summary"),
            ]
        ),
    )
    commands = iter(["first topic", "second topic", "/compact", "/exit"])
    output = []

    run_cli(
        application,
        user_id="user_a",
        session_id="window_1",
        input_fn=lambda _prompt: next(commands),
        output_fn=output.append,
    )

    assert "已完成压缩" in "\n".join(output)
    assert application.summary_repo.get("user_a", "window_1").summary == (
        "manual summary"
    )


def test_cli_todos_context_and_current_commands(tmp_path):
    application = build_application(
        Config(api_key="cli-test", db_path=str(tmp_path / "agent.db")),
        llm_client=ScriptedLLM(
            [
                LLMResponse(
                    content="done",
                    prompt_tokens=12,
                    completion_tokens=4,
                )
            ]
        ),
    )
    application.session_service.create("user_a", "window_1")
    application.todo_repo.add("user_a", "window_1", "CLI todo")
    commands = iter(["hello", "/todos", "/context", "/current", "/exit"])
    output = []

    run_cli(
        application,
        user_id="user_a",
        session_id="window_1",
        input_fn=lambda _prompt: next(commands),
        output_fn=output.append,
    )

    joined = "\n".join(output)
    estimated = application.context_manager.estimate_tokens(
        "user_a",
        "window_1",
    )
    usage = estimated / application.config.max_context_tokens * 100
    assert "CLI todo" in joined
    assert f"Current context estimate: {estimated} tokens" in joined
    assert "Context limit: 32000 tokens" in joined
    assert f"Usage: {usage:.1f}%" in joined
    assert "Prompt: 12" not in joined
    assert "Completion: 4" not in joined
    assert "Current user: user_a" in joined
    assert "Model: deepseek-v4-pro" in joined
