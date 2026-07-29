"""Interactive CLI with persistent Session management."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from mini_agent.bootstrap import Application, build_application
from mini_agent.config import Config
from mini_agent.domain.errors import AgentError


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mini-agent")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--session-id")
    return parser.parse_args(argv)


def _help_text() -> str:
    return "\n".join(
        [
            "/help                       查看帮助",
            "/new                        创建并切换到新 Session",
            "/new <session_id>           创建指定 ID 的 Session",
            "/sessions                   列出当前用户所有 Session",
            "/switch <session_id>        切换到已有 Session",
            "/current                    查看当前 Session",
            "/trace                      查看当前 Session 最近一条 Trace",
            "/trace <trace_id>           查看指定 Trace",
            "/compact                    手动压缩当前 Session",
            "/exit                       退出",
        ]
    )


def run_cli(
    application: Application,
    *,
    user_id: str,
    session_id: str | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    owner = application.session_service.normalize_user_id(user_id)
    current = application.session_service.get_or_create(
        owner,
        session_id or application.session_service.new_session_id(),
    )
    output_fn("Mini Agent Runtime")
    output_fn(f"Current user: {owner}")
    output_fn(f"Current session: {current.id}")
    output_fn(f"Model: {application.config.model}")

    while True:
        try:
            raw = input_fn("user> ")
        except EOFError:
            return
        except KeyboardInterrupt:
            output_fn("输入已取消。")
            continue

        text = raw.strip()
        if not text:
            continue
        command, _, argument = text.partition(" ")
        argument = argument.strip()

        try:
            if command == "/exit":
                return
            if command == "/help":
                output_fn(_help_text())
                continue
            if command == "/new":
                current = application.session_service.create(
                    owner,
                    argument or None,
                )
                output_fn(f"已创建并切换到 {current.id}")
                continue
            if command == "/sessions":
                sessions = application.session_service.list_sessions(owner)
                if not sessions:
                    output_fn("当前用户没有 Session。")
                    continue
                for view in sessions:
                    marker = "*" if view.id == current.id else " "
                    output_fn(
                        f"{marker} {view.id}\n"
                        f"  {view.preview}\n"
                        f"  updated: {view.updated_at}"
                    )
                continue
            if command == "/switch":
                if not argument:
                    output_fn("用法：/switch <session_id>")
                    continue
                current = application.session_service.switch(owner, argument)
                output_fn(f"已切换到 {current.id}")
                continue
            if command == "/current":
                output_fn(f"Current session: {current.id}")
                continue
            if command == "/trace":
                trace = (
                    application.trace_repo.get(argument)
                    if argument
                    else application.trace_repo.get_latest(owner, current.id)
                )
                if (
                    trace is None
                    or trace.user_id != owner
                    or trace.session_id != current.id
                ):
                    output_fn("当前 Session 中未找到该 Trace。")
                    continue
                output_fn(
                    f"Trace: {trace.id}\n"
                    f"Status: {trace.status}\n"
                    f"Session: {trace.session_id}\n"
                    f"Tokens: {trace.total_prompt_tokens} prompt / "
                    f"{trace.total_completion_tokens} completion"
                )
                for step in application.trace_repo.list_steps(trace.id):
                    name = f" {step.name}" if step.name else ""
                    duration = (
                        f" duration={step.duration_ms}ms"
                        if step.duration_ms is not None
                        else ""
                    )
                    error = (
                        f" error={step.error_code}" if step.error_code else ""
                    )
                    output_fn(
                        f"Step {step.step_number}.{step.event_index} "
                        f"{step.event_type}{name} {step.status}{duration}{error}"
                    )
                continue
            if command == "/compact":
                compact_trace_id = application.trace_recorder.start(
                    user_id=owner,
                    session_id=current.id,
                    user_input="/compact",
                )
                compacted = application.context_manager.manual_compact(
                    owner,
                    current.id,
                    trace_id=compact_trace_id,
                )
                application.trace_recorder.complete(
                    compact_trace_id,
                    steps=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                )
                status = "已完成压缩" if compacted.compressed else "没有可压缩的早期消息"
                output_fn(
                    f"{status}，当前估算 {compacted.estimated_tokens} tokens。"
                )
                output_fn(f"Trace ID: {compact_trace_id}")
                continue
            if command.startswith("/"):
                output_fn(f"未知命令：{command}。使用 /help 查看帮助。")
                continue

            def show_tool_event(event: str, name: str, details: dict) -> None:
                if event == "call":
                    output_fn(f"> tool_call {name} {details}")
                else:
                    status = "success" if details.get("success") else "failed"
                    output_fn(f"< tool_result {name} {status}")

            result = application.runtime.run(
                owner,
                current.id,
                text,
                on_tool_event=show_tool_event,
            )
            output_fn(f"assistant> {result.answer}")
            output_fn(f"Trace ID: {result.trace_id}")
        except AgentError as exc:
            output_fn(exc.user_message)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        config = Config.from_env()
        application = build_application(config)
        run_cli(
            application,
            user_id=args.user_id,
            session_id=args.session_id,
        )
    except (AgentError, OSError) as exc:
        message = exc.user_message if isinstance(exc, AgentError) else str(exc)
        print(f"启动失败：{message}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
