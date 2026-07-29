from __future__ import annotations

import os

import pytest

from mini_agent.config import Config
from mini_agent.llm.deepseek_client import DeepSeekClient

pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.getenv("AGENT_API_KEY"), reason="AGENT_API_KEY is not configured")
def test_deepseek_direct_answer():
    client = DeepSeekClient(Config.from_env())

    response = client.chat(
        [
            {
                "role": "user",
                "content": "Reply with exactly: MINI_AGENT_LIVE_OK",
            }
        ]
    )

    assert "MINI_AGENT_LIVE_OK" in response.content
    assert response.tool_calls == []

