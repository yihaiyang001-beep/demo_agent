"""Initial full-history ContextManager, extended with compression in phase 7."""

from __future__ import annotations

import json

from mini_agent.domain.models import ContextResult
from mini_agent.prompts import BASE_SYSTEM_PROMPT
from mini_agent.storage.message_repository import MessageRepository


class ContextManager:
    def __init__(
        self,
        *,
        message_repo: MessageRepository,
        system_prompt: str = BASE_SYSTEM_PROMPT,
    ):
        self.message_repo = message_repo
        self.system_prompt = system_prompt

    def prepare(self, user_id: str, session_id: str) -> ContextResult:
        records = self.message_repo.list_messages(user_id, session_id)
        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.message_repo.to_api_messages(records),
        ]
        serialized = json.dumps(messages, ensure_ascii=False)
        return ContextResult(
            messages=messages,
            estimated_tokens=max(1, len(serialized) // 3),
        )

