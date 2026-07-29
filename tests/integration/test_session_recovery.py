from __future__ import annotations

from mini_agent.session.service import SessionService
from mini_agent.storage.database import Database
from mini_agent.storage.message_repository import MessageRepository
from mini_agent.storage.session_repository import SessionRepository
from mini_agent.storage.summary_repository import SummaryRepository
from mini_agent.storage.todo_repository import TodoRepository


def build_services(db_path):
    database = Database(str(db_path))
    database.initialize()
    message_repo = MessageRepository(database)
    session_repo = SessionRepository(database)
    summary_repo = SummaryRepository(database)
    service = SessionService(
        session_repo=session_repo,
        summary_repo=summary_repo,
        message_repo=message_repo,
    )
    return service, message_repo, TodoRepository(database)


def test_two_sessions_restore_after_repository_restart(tmp_path):
    db_path = tmp_path / "agent.db"
    service, messages, todos = build_services(db_path)
    service.create("user_a", "window_1")
    service.create("user_a", "window_2")
    messages.add_user_message("user_a", "window_1", "窗口一消息")
    messages.add_user_message("user_a", "window_2", "窗口二消息")
    todos.add("user_a", "window_1", "窗口一待办")
    todos.add("user_a", "window_2", "窗口二待办")

    restored_service, restored_messages, restored_todos = build_services(db_path)

    assert restored_service.switch("user_a", "window_1").id == "window_1"
    assert restored_service.switch("user_a", "window_2").id == "window_2"
    assert restored_messages.list_messages("user_a", "window_1")[0].content == "窗口一消息"
    assert restored_messages.list_messages("user_a", "window_2")[0].content == "窗口二消息"
    assert restored_todos.list("user_a", "window_1")[0]["content"] == "窗口一待办"
    assert restored_todos.list("user_a", "window_2")[0]["content"] == "窗口二待办"

