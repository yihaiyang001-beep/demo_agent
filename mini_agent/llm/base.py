"""LLM client interface used by the runtime and test fakes."""

from __future__ import annotations

from typing import Any, Protocol

from mini_agent.domain.models import LLMResponse


class LLMClient(Protocol):
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...

