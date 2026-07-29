"""Base classes for schema-driven runtime tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from mini_agent.domain.models import ToolRuntimeContext


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BaseTool(ABC):
    name: str
    description: str
    args_model: type[ToolArgs]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.args_model.model_json_schema(),
            },
        }

    def validate(self, arguments: dict[str, Any]) -> ToolArgs:
        return self.args_model.model_validate(arguments)

    @abstractmethod
    def execute(self, args: ToolArgs, context: ToolRuntimeContext) -> dict[str, Any]:
        """Execute a validated call and return compact JSON-compatible data."""

