from __future__ import annotations

from mini_agent.tools.search import MockSearchTool, SearchArgs


def test_search_returns_deterministic_results(runtime_context):
    tool = MockSearchTool()

    first = tool.execute(SearchArgs(query="agent runtime"), runtime_context)
    second = tool.execute(SearchArgs(query="agent runtime"), runtime_context)

    assert first == second
    assert first["results"][0]["title"] == "Agent Runtime Overview"


def test_search_marks_result_as_mock(runtime_context):
    result = MockSearchTool().execute(SearchArgs(query="tool"), runtime_context)
    assert result["mock"] is True


def test_search_top_k_limit(runtime_context):
    result = MockSearchTool().execute(
        SearchArgs(query="context session tool agent", top_k=2),
        runtime_context,
    )
    assert len(result["results"]) == 2


def test_search_no_match(runtime_context):
    result = MockSearchTool().execute(
        SearchArgs(query="unfindable-zebra-987"),
        runtime_context,
    )
    assert result["results"] == []

