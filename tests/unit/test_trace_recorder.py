from __future__ import annotations

from mini_agent.storage.database import Database
from mini_agent.storage.session_repository import SessionRepository
from mini_agent.storage.trace_repository import TraceRepository
from mini_agent.trace.recorder import TraceRecorder


def test_retry_observer_records_retry_step(tmp_path):
    database = Database(str(tmp_path / "agent.db"))
    database.initialize()
    SessionRepository(database).create("user_a", "window_1")
    repository = TraceRepository(database)
    recorder = TraceRecorder(repository)
    trace_id = recorder.start(
        user_id="user_a",
        session_id="window_1",
        user_input="hello",
    )
    recorder.begin_llm_step(trace_id, 2)

    recorder.record_retry(1, "APITimeoutError", 1000)
    recorder.end_llm_step()

    step = repository.list_steps(trace_id)[0]
    assert step.event_type == "retry"
    assert step.step_number == 2
    assert step.error_code == "APITimeoutError"
    assert step.duration_ms == 1000

