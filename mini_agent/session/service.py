"""Owner-scoped Session creation, lookup, preview, and recovery."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from mini_agent.domain.errors import InvalidUserInputError, SessionNotFoundError
from mini_agent.domain.models import SessionRecord, SessionView
from mini_agent.storage.message_repository import MessageRepository
from mini_agent.storage.session_repository import SessionRepository
from mini_agent.storage.summary_repository import SummaryRepository

MAX_USER_ID_LENGTH = 100
MAX_SESSION_ID_LENGTH = 100


def _normalize_identifier(value: str, *, field: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise InvalidUserInputError(f"{field} must be a string")
    collapsed = re.sub(r"\s+", "-", value.strip())
    normalized = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in collapsed
    )
    normalized = re.sub(r"-+", "-", normalized).strip(".-_")
    normalized = normalized[:max_length].strip(".-_")
    if not normalized:
        raise InvalidUserInputError(f"{field} must not be empty")
    return normalized


class SessionService:
    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        summary_repo: SummaryRepository,
        message_repo: MessageRepository,
    ):
        self.session_repo = session_repo
        self.summary_repo = summary_repo
        self.message_repo = message_repo

    @staticmethod
    def normalize_user_id(user_id: str) -> str:
        return _normalize_identifier(
            user_id,
            field="user_id",
            max_length=MAX_USER_ID_LENGTH,
        )

    @staticmethod
    def normalize_session_id(session_id: str) -> str:
        return _normalize_identifier(
            session_id,
            field="session_id",
            max_length=MAX_SESSION_ID_LENGTH,
        )

    @staticmethod
    def new_session_id() -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"session_{timestamp}_{uuid.uuid4().hex[:8]}"

    def create(
        self,
        user_id: str,
        session_id: str | None = None,
    ) -> SessionRecord:
        owner = self.normalize_user_id(user_id)
        normalized_id = self.normalize_session_id(session_id or self.new_session_id())
        if self.session_repo.get(owner, normalized_id) is not None:
            raise InvalidUserInputError(
                f"Session already exists: {normalized_id}",
                user_message=f"会话已存在：{normalized_id}",
            )
        return self.session_repo.create(owner, normalized_id)

    def get_or_create(self, user_id: str, session_id: str) -> SessionRecord:
        owner = self.normalize_user_id(user_id)
        normalized_id = self.normalize_session_id(session_id)
        existing = self.session_repo.get(owner, normalized_id)
        return existing or self.session_repo.create(owner, normalized_id)

    def switch(self, user_id: str, session_id: str) -> SessionRecord:
        owner = self.normalize_user_id(user_id)
        normalized_id = self.normalize_session_id(session_id)
        record = self.session_repo.get(owner, normalized_id)
        if record is None:
            raise SessionNotFoundError(
                f"Session not found for owner: {owner}/{normalized_id}",
                user_message=f"未找到会话：{normalized_id}",
            )
        return record

    def list_sessions(self, user_id: str, limit: int = 50) -> list[SessionView]:
        owner = self.normalize_user_id(user_id)
        views = []
        for record in self.session_repo.list_by_user(owner, limit):
            summary = self.summary_repo.get(owner, record.id)
            first_message = self.message_repo.get_first_user_message(owner, record.id)
            preview_source = (
                summary.summary
                if summary is not None
                else record.title or first_message or "空会话"
            )
            preview = re.sub(r"\s+", " ", preview_source).strip()[:80]
            views.append(
                SessionView(
                    user_id=record.user_id,
                    id=record.id,
                    title=record.title,
                    preview=preview,
                    status=record.status,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
            )
        return views

    def touch_and_set_title_if_empty(
        self,
        user_id: str,
        session_id: str,
        first_user_message: str,
    ) -> None:
        title = re.sub(r"\s+", " ", first_user_message).strip()[:40]
        if title:
            self.session_repo.update_title_if_empty(user_id, session_id, title)
        else:
            self.session_repo.touch(user_id, session_id)

    def set_status(self, user_id: str, session_id: str, status: str) -> None:
        owner = self.normalize_user_id(user_id)
        normalized_id = self.normalize_session_id(session_id)
        self.session_repo.set_status(owner, normalized_id, status)

    def recover_stale_busy(self) -> list[SessionRecord]:
        return self.session_repo.reset_status("busy", "idle")
