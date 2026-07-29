"""Dependency assembly entry points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Config
from .context.manager import ContextManager
from .llm.deepseek_client import DeepSeekClient
from .runtime.agent_runtime import AgentRuntime
from .session.service import SessionService
from .storage.database import Database
from .storage.message_repository import MessageRepository
from .storage.session_repository import SessionRepository
from .storage.summary_repository import SummaryRepository
from .storage.todo_repository import TodoRepository
from .storage.trace_repository import TraceRepository
from .tools.calculator import CalculatorTool
from .tools.registry import ToolRegistry
from .tools.search import MockSearchTool
from .tools.todo import TodoTool
from .tools.weather import WeatherTool
from .trace.recorder import TraceRecorder


@dataclass(frozen=True)
class Application:
    config: Config
    database: Database
    session_service: SessionService
    message_repo: MessageRepository
    summary_repo: SummaryRepository
    todo_repo: TodoRepository
    trace_repo: TraceRepository
    tool_registry: ToolRegistry
    context_manager: ContextManager
    trace_recorder: TraceRecorder
    runtime: AgentRuntime


def initialize_foundation(config: Config) -> Database:
    """Create and initialize the storage dependency used by later phases."""
    database = Database(config.db_path)
    database.initialize()
    return database


def build_application(
    config: Config,
    *,
    llm_client: Any | None = None,
    tool_registry: ToolRegistry | None = None,
) -> Application:
    database = initialize_foundation(config)
    session_repo = SessionRepository(database)
    message_repo = MessageRepository(database)
    summary_repo = SummaryRepository(database)
    todo_repo = TodoRepository(database)
    trace_repo = TraceRepository(database)
    session_service = SessionService(
        session_repo=session_repo,
        summary_repo=summary_repo,
        message_repo=message_repo,
    )
    registry = tool_registry or ToolRegistry()
    if tool_registry is None:
        registry.register(CalculatorTool())
        registry.register(WeatherTool(config))
        registry.register(TodoTool(todo_repo))
        registry.register(MockSearchTool())
    trace_recorder = TraceRecorder(trace_repo, sensitive_values=[config.api_key])
    for stale_session in session_service.recover_stale_busy():
        recovery_trace_id = trace_recorder.start(
            user_id=stale_session.user_id,
            session_id=stale_session.id,
            user_input="[startup recovery]",
        )
        trace_recorder.record_event(
            recovery_trace_id,
            step_number=0,
            event_index=0,
            event_type="stale_busy_recovered",
            status="success",
            output_data={"previous_status": "busy", "new_status": "idle"},
        )
        trace_recorder.complete(
            recovery_trace_id,
            steps=0,
            prompt_tokens=0,
            completion_tokens=0,
        )
    active_llm_client = llm_client or DeepSeekClient(
        config,
        on_retry=trace_recorder.record_retry,
    )
    context_manager = ContextManager(
        config=config,
        llm_client=active_llm_client,
        message_repo=message_repo,
        summary_repo=summary_repo,
        tool_registry=registry,
        trace_recorder=trace_recorder,
    )
    runtime = AgentRuntime(
        config=config,
        session_service=session_service,
        message_repo=message_repo,
        context_manager=context_manager,
        llm_client=active_llm_client,
        tool_registry=registry,
        trace_recorder=trace_recorder,
    )
    return Application(
        config=config,
        database=database,
        session_service=session_service,
        message_repo=message_repo,
        summary_repo=summary_repo,
        todo_repo=todo_repo,
        trace_repo=trace_repo,
        tool_registry=registry,
        context_manager=context_manager,
        trace_recorder=trace_recorder,
        runtime=runtime,
    )
