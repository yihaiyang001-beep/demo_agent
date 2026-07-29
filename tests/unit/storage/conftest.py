from __future__ import annotations

import pytest

from mini_agent.session.service import SessionService
from mini_agent.storage.database import Database
from mini_agent.storage.message_repository import MessageRepository
from mini_agent.storage.session_repository import SessionRepository
from mini_agent.storage.summary_repository import SummaryRepository
from mini_agent.storage.trace_repository import TraceRepository


@pytest.fixture
def storage(tmp_path):
    database = Database(str(tmp_path / "agent.db"))
    database.initialize()
    session_repo = SessionRepository(database)
    message_repo = MessageRepository(database)
    summary_repo = SummaryRepository(database)
    trace_repo = TraceRepository(database)
    service = SessionService(
        session_repo=session_repo,
        summary_repo=summary_repo,
        message_repo=message_repo,
    )
    return {
        "database": database,
        "session_repo": session_repo,
        "message_repo": message_repo,
        "summary_repo": summary_repo,
        "trace_repo": trace_repo,
        "service": service,
    }

