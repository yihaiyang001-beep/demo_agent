"""Replaceable prompt-size estimation."""

from __future__ import annotations

import json
from typing import Any, Protocol


class TokenEstimator(Protocol):
    def estimate_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> int: ...


class SimpleTokenEstimator:
    """Conservative three-characters-per-token estimate for mixed zh/en JSON."""

    def estimate_messages(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> int:
        serialized = json.dumps(
            {"messages": messages, "tools": tools or []},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return max(1, len(serialized) // 3)

