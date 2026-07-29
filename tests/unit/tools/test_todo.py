from __future__ import annotations

import pytest
from pydantic import ValidationError

from mini_agent.domain.models import ToolRuntimeContext
from mini_agent.storage.todo_repository import TodoRepository
from mini_agent.tools.todo import TodoArgs, TodoTool


def make_tool(database):
    return TodoTool(TodoRepository(database))


def test_todo_add_and_list(todo_database, runtime_context):
    tool = make_tool(todo_database)
    added = tool.execute(
        TodoArgs(action="add", content="明天带伞"),
        runtime_context,
    )
    listed = tool.execute(TodoArgs(action="list"), runtime_context)

    assert added["todo"]["content"] == "明天带伞"
    assert added["todo"]["status"] == "pending"
    assert listed["count"] == 1
    assert listed["todos"][0]["id"] == added["todo"]["id"]


def test_todo_complete(todo_database, runtime_context):
    tool = make_tool(todo_database)
    todo_id = tool.execute(
        TodoArgs(action="add", content="完成测试"),
        runtime_context,
    )["todo"]["id"]

    result = tool.execute(
        TodoArgs(action="complete", todo_id=todo_id),
        runtime_context,
    )

    assert result["todo"]["status"] == "completed"
    assert result["todo"]["completed_at"]


def test_todo_delete(todo_database, runtime_context):
    tool = make_tool(todo_database)
    todo_id = tool.execute(
        TodoArgs(action="add", content="临时待办"),
        runtime_context,
    )["todo"]["id"]

    result = tool.execute(
        TodoArgs(action="delete", todo_id=todo_id),
        runtime_context,
    )

    assert result == {"action": "delete", "todo_id": todo_id}
    assert tool.execute(TodoArgs(action="list"), runtime_context)["count"] == 0


def test_todo_requires_content_for_add():
    with pytest.raises(ValidationError):
        TodoArgs(action="add")


def test_todo_requires_id_for_complete():
    with pytest.raises(ValidationError):
        TodoArgs(action="complete")


def test_todo_isolated_by_session(todo_database, runtime_context):
    tool = make_tool(todo_database)
    tool.execute(TodoArgs(action="add", content="window one"), runtime_context)
    other_context = ToolRuntimeContext(
        user_id="user_a",
        session_id="window_2",
        trace_id="trace_other",
    )

    assert tool.execute(TodoArgs(action="list"), other_context)["todos"] == []


def test_todo_persists_after_new_repository_instance(todo_database, runtime_context):
    make_tool(todo_database).execute(
        TodoArgs(action="add", content="persistent"),
        runtime_context,
    )

    restored = make_tool(todo_database).execute(
        TodoArgs(action="list"),
        runtime_context,
    )

    assert restored["count"] == 1
    assert restored["todos"][0]["content"] == "persistent"

