from __future__ import annotations

from collections import deque
from typing import Any

from mini_agent.domain.models import LLMResponse


class ScriptedLLM:
    def __init__(self, responses: list[LLMResponse | Exception]):
        self.responses = deque(responses)
        self.requests: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.requests.append({"messages": messages, "tools": tools})
        if not self.responses:
            raise AssertionError("No scripted LLM response left")
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response

