"""Persistent summary and whole-message-group Context management."""

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any

from mini_agent.config import Config
from mini_agent.domain.errors import ContextLimitExceededError
from mini_agent.domain.models import ContextResult, MessageRecord, SummaryRecord
from mini_agent.llm.base import LLMClient
from mini_agent.prompts import BASE_SYSTEM_PROMPT
from mini_agent.storage.message_repository import MessageRepository
from mini_agent.storage.summary_repository import SummaryRepository
from mini_agent.tools.registry import ToolRegistry
from mini_agent.trace.recorder import TraceRecorder

from .compressor import ContextCompressor
from .message_groups import (
    flatten_groups,
    group_messages,
    split_recent_groups,
)
from .token_estimator import SimpleTokenEstimator, TokenEstimator


class ContextManager:
    def __init__(
        self,
        *,
        config: Config,
        llm_client: LLMClient,
        message_repo: MessageRepository,
        summary_repo: SummaryRepository,
        tool_registry: ToolRegistry,
        trace_recorder: TraceRecorder,
        token_estimator: TokenEstimator | None = None,
        system_prompt: str = BASE_SYSTEM_PROMPT,
    ):
        self.config = config
        self.message_repo = message_repo
        self.summary_repo = summary_repo
        self.tool_registry = tool_registry
        self.trace_recorder = trace_recorder
        self.token_estimator = token_estimator or SimpleTokenEstimator()
        self.system_prompt = system_prompt
        self.compressor = ContextCompressor(llm_client)

    def prepare(
        self,
        user_id: str,
        session_id: str,
        *,
        trace_id: str | None = None,
        step_number: int = 0,
    ) -> ContextResult:
        summary = self.summary_repo.get(user_id, session_id)
        active_records = self._active_records(user_id, session_id, summary)
        messages = self._build_messages(summary, active_records)
        estimated = self._estimate(messages)
        initial_estimated = estimated
        compressed = False

        summary_threshold = round(
            self.config.max_context_tokens * self.config.summary_threshold_ratio
        )
        if estimated >= summary_threshold:
            compressed = self._compress_older_groups(
                user_id,
                session_id,
                active_records,
                summary,
                keep_messages=self.config.recent_messages,
                trace_id=trace_id,
                step_number=step_number,
                before_tokens=estimated,
            )
            if compressed:
                summary = self.summary_repo.get(user_id, session_id)
                active_records = self._active_records(user_id, session_id, summary)
                messages = self._build_messages(summary, active_records)
                estimated = self._estimate(messages)

        collapse_threshold = round(
            self.config.max_context_tokens * self.config.collapse_threshold_ratio
        )
        if estimated >= collapse_threshold:
            groups = group_messages(active_records)
            _, recent = split_recent_groups(
                groups,
                self.config.collapse_recent_messages,
            )
            active_records = flatten_groups(recent)
            messages = self._build_messages(summary, active_records)
            estimated = self._estimate(messages)
            self._record_context_event(
                trace_id,
                step_number,
                "context_collapsed",
                {
                    "before_tokens": initial_estimated,
                    "after_tokens": estimated,
                    "kept_first_message_id": (
                        active_records[0].id if active_records else None
                    ),
                },
            )

        if estimated > self.config.max_context_tokens:
            for max_chars in (1500, 600, 200):
                messages = self._truncate_tool_results(messages, max_chars)
                estimated = self._estimate(messages)
                if estimated <= self.config.max_context_tokens:
                    break

        if estimated > self.config.max_context_tokens:
            raise ContextLimitExceededError(
                f"Estimated context {estimated} exceeds "
                f"soft limit {self.config.max_context_tokens}"
            )

        return ContextResult(
            messages=messages,
            estimated_tokens=estimated,
            compressed=compressed,
        )

    def manual_compact(
        self,
        user_id: str,
        session_id: str,
        *,
        trace_id: str | None = None,
    ) -> ContextResult:
        summary = self.summary_repo.get(user_id, session_id)
        active_records = self._active_records(user_id, session_id, summary)
        before = self._estimate(self._build_messages(summary, active_records))
        compressed = self._compress_older_groups(
            user_id,
            session_id,
            active_records,
            summary,
            keep_messages=1,
            trace_id=trace_id,
            step_number=0,
            before_tokens=before,
        )
        result = self.prepare(
            user_id,
            session_id,
            trace_id=trace_id,
            step_number=0,
        )
        return ContextResult(
            messages=result.messages,
            estimated_tokens=result.estimated_tokens,
            compressed=compressed or result.compressed,
        )

    def _compress_older_groups(
        self,
        user_id: str,
        session_id: str,
        active_records: list[MessageRecord],
        previous_summary: SummaryRecord | None,
        *,
        keep_messages: int,
        trace_id: str | None,
        step_number: int,
        before_tokens: int,
    ) -> bool:
        older, _ = split_recent_groups(
            group_messages(active_records),
            keep_messages,
        )
        if not older:
            return False
        boundary = older[-1].last_id
        started = time.perf_counter()
        try:
            updated_summary = self.compressor.compress(
                previous_summary.summary if previous_summary else None,
                older,
            )
            self.summary_repo.upsert(
                user_id,
                session_id,
                updated_summary,
                boundary,
            )
        except Exception as exc:
            self._record_context_event(
                trace_id,
                step_number,
                "context_compression_failed",
                {
                    "before_tokens": before_tokens,
                    "boundary_message_id": boundary,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                status="failed",
            )
            return False

        duration_ms = round((time.perf_counter() - started) * 1000)
        new_summary = self.summary_repo.get(user_id, session_id)
        remaining = self._active_records(user_id, session_id, new_summary)
        after_tokens = self._estimate(self._build_messages(new_summary, remaining))
        self._record_context_event(
            trace_id,
            step_number,
            "context_compressed",
            {
                "before_tokens": before_tokens,
                "after_tokens": after_tokens,
                "summarized_until_message_id": boundary,
                "duration_ms": duration_ms,
            },
        )
        return True

    def _active_records(
        self,
        user_id: str,
        session_id: str,
        summary: SummaryRecord | None,
    ) -> list[MessageRecord]:
        if summary is None:
            return self.message_repo.list_messages(user_id, session_id)
        return self.message_repo.list_messages_after(
            user_id,
            session_id,
            summary.summarized_until_message_id,
        )

    def _build_messages(
        self,
        summary: SummaryRecord | None,
        records: list[MessageRecord],
    ) -> list[dict[str, Any]]:
        system_content = self.system_prompt
        if summary is not None:
            system_content += (
                "\n\n[SESSION SUMMARY]\n"
                + summary.summary
                + "\n[END SESSION SUMMARY]"
            )
        return [
            {"role": "system", "content": system_content},
            *self.message_repo.to_api_messages(records),
        ]

    def _estimate(self, messages: list[dict[str, Any]]) -> int:
        return self.token_estimator.estimate_messages(
            messages,
            self.tool_registry.schemas(),
        )

    def _record_context_event(
        self,
        trace_id: str | None,
        step_number: int,
        event_type: str,
        output_data: dict[str, Any],
        *,
        status: str = "success",
    ) -> None:
        if trace_id is None:
            return
        self.trace_recorder.record_event(
            trace_id,
            step_number=step_number,
            event_index=-1,
            event_type=event_type,
            status=status,
            output_data=output_data,
        )

    @staticmethod
    def _truncate_tool_results(
        messages: list[dict[str, Any]],
        max_chars: int,
    ) -> list[dict[str, Any]]:
        truncated = deepcopy(messages)
        for message in truncated:
            if message.get("role") != "tool":
                continue
            content = str(message.get("content") or "")
            if len(content) <= max_chars:
                continue
            preview_size = max(20, max_chars // 2)
            message["content"] = json.dumps(
                {
                    "success": False,
                    "data": None,
                    "error_code": "CONTEXT_TOOL_RESULT_TRUNCATED",
                    "message": (
                        content[:preview_size]
                        + f"...[{len(content)} chars truncated]..."
                        + content[-preview_size:]
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        return truncated

