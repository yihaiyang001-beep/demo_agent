"""Conversation grouping that never separates Tool Calls from their results."""

from __future__ import annotations

from dataclasses import dataclass

from mini_agent.domain.models import MessageRecord


@dataclass(frozen=True)
class MessageGroup:
    messages: list[MessageRecord]
    first_id: int
    last_id: int


def group_messages(records: list[MessageRecord]) -> list[MessageGroup]:
    if not records:
        return []
    grouped: list[list[MessageRecord]] = []
    current: list[MessageRecord] = []
    for record in records:
        if record.role == "user" and current:
            grouped.append(current)
            current = []
        current.append(record)
    if current:
        grouped.append(current)
    return [
        MessageGroup(
            messages=messages,
            first_id=messages[0].id,
            last_id=messages[-1].id,
        )
        for messages in grouped
    ]


def split_recent_groups(
    groups: list[MessageGroup],
    target_messages: int,
) -> tuple[list[MessageGroup], list[MessageGroup]]:
    """Return ``(older, recent)`` while always keeping the last group whole."""
    if not groups:
        return [], []
    recent_reversed: list[MessageGroup] = []
    selected_messages = 0
    for group in reversed(groups):
        group_size = len(group.messages)
        if recent_reversed and selected_messages + group_size > target_messages:
            break
        recent_reversed.append(group)
        selected_messages += group_size
    recent = list(reversed(recent_reversed))
    return groups[: len(groups) - len(recent)], recent


def flatten_groups(groups: list[MessageGroup]) -> list[MessageRecord]:
    return [record for group in groups for record in group.messages]

