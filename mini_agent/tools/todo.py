"""Session-scoped persistent Todo tool."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from mini_agent.domain.errors import ToolExecutionError
from mini_agent.domain.models import ToolRuntimeContext
from mini_agent.storage.todo_repository import TodoRepository

from .base import BaseTool, ToolArgs


class TodoArgs(ToolArgs):
    action: Literal["add", "list", "complete", "delete"]
    content: str | None = Field(default=None, max_length=500)
    todo_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action == "add" and not self.content:
            raise ValueError("add 操作必须提供 content")
        if self.action in {"complete", "delete"} and self.todo_id is None:
            raise ValueError(f"{self.action} 操作必须提供 todo_id")
        return self


class TodoTool(BaseTool):
    name = "todo"
    description = "Add, list, complete, or delete todos in the current session."
    args_model = TodoArgs

    def __init__(self, repository: TodoRepository):
        self.repository = repository

    def execute(self, args: ToolArgs, context: ToolRuntimeContext) -> dict[str, Any]:
        assert isinstance(args, TodoArgs)
        if args.action == "add":
            todo = self.repository.add(
                context.user_id,
                context.session_id,
                args.content or "",
            )
            return {"action": "add", "todo": todo}

        if args.action == "list":
            todos = self.repository.list(context.user_id, context.session_id)
            return {"action": "list", "todos": todos, "count": len(todos)}

        if args.action == "complete":
            todo = self.repository.complete(
                context.user_id,
                context.session_id,
                args.todo_id or 0,
            )
            if todo is None:
                raise ToolExecutionError("TODO_NOT_FOUND", "当前会话中不存在该待办")
            return {"action": "complete", "todo": todo}

        deleted = self.repository.delete(
            context.user_id,
            context.session_id,
            args.todo_id or 0,
        )
        if not deleted:
            raise ToolExecutionError("TODO_NOT_FOUND", "当前会话中不存在该待办")
        return {"action": "delete", "todo_id": args.todo_id}

