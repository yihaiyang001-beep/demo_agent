"""Deterministic local mock search."""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field

from mini_agent.domain.models import ToolRuntimeContext

from .base import BaseTool, ToolArgs

MOCK_DOCUMENTS = [
    {
        "title": "Agent Runtime Overview",
        "keywords": ["agent", "runtime", "loop"],
        "snippet": "Agent Runtime coordinates the LLM, tools, session and context.",
        "url": "mock://agent-runtime-overview",
    },
    {
        "title": "Tool Calling Guide",
        "keywords": ["tool", "calling", "function", "schema"],
        "snippet": "Tool calling lets a model request validated external operations.",
        "url": "mock://tool-calling-guide",
    },
    {
        "title": "Persistent Session Memory",
        "keywords": ["session", "memory", "sqlite", "history"],
        "snippet": "Persistent sessions restore isolated history from SQLite.",
        "url": "mock://persistent-session-memory",
    },
    {
        "title": "Context Compression Notes",
        "keywords": ["context", "compression", "summary", "token"],
        "snippet": "Context compression preserves key facts while limiting prompt size.",
        "url": "mock://context-compression-notes",
    },
]


class SearchArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=200)
    top_k: int = Field(default=3, ge=1, le=5)


class MockSearchTool(BaseTool):
    name = "search"
    description = "Search a small deterministic local mock knowledge base."
    args_model = SearchArgs

    def execute(self, args: ToolArgs, context: ToolRuntimeContext) -> dict[str, Any]:
        assert isinstance(args, SearchArgs)
        terms = {
            term
            for term in re.findall(r"[\w\u4e00-\u9fff]+", args.query.lower())
            if term
        }
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for index, document in enumerate(MOCK_DOCUMENTS):
            title_terms = set(re.findall(r"[\w\u4e00-\u9fff]+", document["title"].lower()))
            keywords = {keyword.lower() for keyword in document["keywords"]}
            searchable = title_terms | keywords
            score = sum(2 if term in keywords else 1 for term in terms & searchable)
            if score:
                scored.append((score, index, document))

        scored.sort(key=lambda item: (-item[0], item[1]))
        results = [
            {
                "title": document["title"],
                "snippet": document["snippet"],
                "url": document["url"],
            }
            for _, _, document in scored[: args.top_k]
        ]
        return {
            "query": args.query,
            "mock": True,
            "results": results,
        }

