"""Cumulative LLM summary generation."""

from __future__ import annotations

import json

from mini_agent.domain.errors import EmptyLLMResponseError
from mini_agent.llm.base import LLMClient
from mini_agent.prompts import SUMMARY_PROMPT

from .message_groups import MessageGroup


def _history_for_summary(groups: list[MessageGroup]) -> str:
    lines: list[str] = []
    tool_names: dict[str, str] = {}
    todo_values: set[str] = set()
    for group in groups:
        for record in group.messages:
            for raw_call in record.tool_calls or []:
                function = raw_call.get("function") or {}
                if function.get("name") != "todo":
                    continue
                try:
                    arguments = json.loads(str(function.get("arguments") or "{}"))
                except json.JSONDecodeError:
                    continue
                if isinstance(arguments, dict) and arguments.get("content"):
                    todo_values.add(str(arguments["content"]))

    def without_todo_values(text: str) -> str:
        sanitized = text
        for todo_value in todo_values:
            sanitized = sanitized.replace(todo_value, "[TODO CONTENT OMITTED]")
        return sanitized

    for group in groups:
        for record in group.messages:
            if record.role == "assistant" and record.tool_calls:
                if record.content:
                    lines.append(
                        f"[assistant] {without_todo_values(record.content)[:1000]}"
                    )
                for raw_call in record.tool_calls:
                    function = raw_call.get("function") or {}
                    name = str(function.get("name") or "")
                    call_id = str(raw_call.get("id") or "")
                    tool_names[call_id] = name
                    if name == "todo":
                        continue
                    arguments = without_todo_values(
                        str(function.get("arguments") or "{}")
                    )
                    lines.append(
                        f"[assistant tool_call {name}] {arguments[:1000]}"
                    )
                continue
            if record.role == "tool":
                name = tool_names.get(record.tool_call_id or "", "unknown")
                if name == "todo":
                    continue
                lines.append(
                    f"[tool {name}] {without_todo_values(record.content or '')[:1000]}"
                )
                continue
            lines.append(
                f"[{record.role}] {without_todo_values(record.content or '')[:2000]}"
            )
    return "\n".join(lines)


class ContextCompressor:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def compress(
        self,
        previous_summary: str | None,
        groups: list[MessageGroup],
    ) -> str:
        summary_input = (
            "[PREVIOUS SUMMARY]\n"
            + (previous_summary or "(none)")
            + "\n\n[NEW HISTORY]\n"
            + _history_for_summary(groups)
        )
        response = self.llm_client.chat(
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": summary_input},
            ],
            tools=None,
        )
        if response.tool_calls or not response.content.strip():
            raise EmptyLLMResponseError("Summary model returned an invalid response")
        return response.content.strip()
