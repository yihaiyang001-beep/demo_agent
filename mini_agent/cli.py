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
            if command.startswith("/"):
                output_fn(f"未知命令：{command}。使用 /help 查看帮助。")
                continue

            application.message_repo.add_user_message(owner, current.id, text)
            application.session_service.touch_and_set_title_if_empty(
                owner,
                current.id,
                text,
            )
            reply = f"echo: {text}"
            application.message_repo.add_assistant_message(owner, current.id, reply)
            output_fn(f"assistant> {reply}")
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

