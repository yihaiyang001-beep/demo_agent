"""Dependency assembly entry points."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .session.service import SessionService
from .storage.database import Database
from .storage.message_repository import MessageRepository
from .storage.session_repository import SessionRepository
from .storage.summary_repository import SummaryRepository
from .storage.todo_repository import TodoRepository
from .storage.trace_repository import TraceRepository


@dataclass(frozen=True)
class Application:
    config: Config
    database: Database
    session_service: SessionService
    message_repo: MessageRepository
    summary_repo: SummaryRepository
    todo_repo: TodoRepository
    trace_repo: TraceRepository


def initialize_foundation(config: Config) -> Database:
    """Create and initialize the storage dependency used by later phases."""
    database = Database(config.db_path)
    database.initialize()
    return database


def build_application(config: Config) -> Application:
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
    return Application(
        config=config,
        database=database,
        session_service=session_service,
        message_repo=message_repo,
        summary_repo=summary_repo,
        todo_repo=todo_repo,
        trace_repo=trace_repo,
    )

