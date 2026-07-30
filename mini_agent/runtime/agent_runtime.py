"""Synchronous multi-step Agent Loop."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Any

from mini_agent.config import Config
from mini_agent.context.manager import ContextManager
from mini_agent.domain.errors import (
    AgentError,
    EmptyLLMResponseError,
    InvalidUserInputError,
)
from mini_agent.domain.models import AgentResult, ToolResult, ToolRuntimeContext
from mini_agent.llm.base import LLMClient
from mini_agent.session.service import SessionService
from mini_agent.storage.message_repository import MessageRepository
from mini_agent.tools.registry import ToolRegistry
from mini_agent.trace.recorder import TraceRecorder

from .repetition_guard import RepetitionGuard

ToolEventCallback = Callable[[str, str, dict[str, Any]], None]


class AgentRuntime:
    def __init__(
        self,
        *,
        config: Config,
        session_service: SessionService,
        message_repo: MessageRepository,
        context_manager: ContextManager,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        trace_recorder: TraceRecorder,
    ):
        self.config = config
        self.session_service = session_service
        self.message_repo = message_repo
        self.context_manager = context_manager
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.trace_recorder = trace_recorder

    def run(
        self,
        user_id: str,
        session_id: str,
        user_input: str,
        *,
        on_tool_event: ToolEventCallback | None = None,
    ) -> AgentResult:
        # 阶段一、 初始化与状态修复（进入循环前）
        # 校验与取数：验证 user_id 等输入，获取或创建会话（Session）。
        #
        # 状态锁定：将当前会话状态设为 "busy"（防止并发冲突）。
        #
        # 关键修复：调用 repair_pending_tool_calls。这是为了处理上一次运行中途崩溃导致的“悬空”工具调用（AI 要求调用工具，但结果未返回），确保消息历史的一致性。
        #
        # 记录用户输入：将用户问题存入消息库，并根据内容自动生成会话标题。
        self._validate_input(user_id, session_id, user_input)
        # 加载或者创建session
        session = self.session_service.get_or_create(user_id, session_id)
        owner = session.user_id
        current_session_id = session.id
        content = user_input.strip()
        # 为本次对话开启一个trace
        trace_id = self.trace_recorder.start(
            user_id=owner,
            session_id=current_session_id,
            user_input=content,
        )
        # 创建重复调用保护器
        repeat_guard = RepetitionGuard(self.config.repeat_limit)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        completed_steps = 0

        try:
            # 设置session状态
            self.session_service.set_status(owner, current_session_id, "busy")
            # 补全上次调用失败的tool
            repaired_ids = self.message_repo.repair_pending_tool_calls(
                owner,
                current_session_id,
            )
            if repaired_ids:
                self.trace_recorder.record_event(
                    trace_id,
                    step_number=0,
                    event_index=0,
                    event_type="tool_calls_repaired",
                    status="success",
                    output_data={"tool_call_ids": repaired_ids},
                )
            # 加入信息，设置session标题（若是第一条信息就截取提问的前四十个字符为title）
            self.message_repo.add_user_message(owner, current_session_id, content)
            self.session_service.touch_and_set_title_if_empty(
                owner,
                current_session_id,
                content,
            )
            # 阶段二：核心迭代循环（Step 1 → Max_Steps）
            for step_number in range(1, self.config.max_steps + 1):
                completed_steps = step_number
                # 获取上下文，这一步就可能涉及到压缩上下文
                context = self.context_manager.prepare(
                    owner,
                    current_session_id,
                    trace_id=trace_id,
                    step_number=step_number,
                )
                # 记录事件
                self.trace_recorder.record_context(
                    trace_id,
                    step_number,
                    context.estimated_tokens,
                )
                self.trace_recorder.begin_llm_step(trace_id, step_number)

                try:
                    # 调用llm，获取一个response，传入tool.schemas和消息
                    response = self.llm_client.chat(
                        messages=context.messages,
                        tools=self.tool_registry.schemas(),
                    )
                finally:
                    self.trace_recorder.end_llm_step()
                total_prompt_tokens += response.prompt_tokens
                total_completion_tokens += response.completion_tokens
                self.trace_recorder.record_llm_decision(
                    trace_id,
                    step_number,
                    response,
                )

                # 重要分支，若无tool调用就说明回答结束，直接返回给用户即可
                if not response.tool_calls:
                    if not response.content.strip():
                        raise EmptyLLMResponseError("LLM returned no content or tool calls")
                    answer = response.content.strip()
                    self.message_repo.add_assistant_message(
                        owner,
                        current_session_id,
                        answer,
                    )
                    self.trace_recorder.complete(
                        trace_id,
                        steps=step_number,
                        prompt_tokens=total_prompt_tokens,
                        completion_tokens=total_completion_tokens,
                    )
                    return AgentResult(
                        status="completed",
                        answer=answer,
                        trace_id=trace_id,
                        steps=step_number,
                        prompt_tokens=total_prompt_tokens,
                        completion_tokens=total_completion_tokens,
                    )

                # 反之就直接去调用tool，进入下一轮循环

                # 保存message
                self.message_repo.add_assistant_tool_calls(
                    owner,
                    current_session_id,
                    response.tool_calls,
                    response.content or None,
                )

                # 按顺序执行tool
                for index, tool_call in enumerate(response.tool_calls):
                    call_event_index = 3 + index * 2
                    # 记录工具调用trace
                    self.trace_recorder.record_tool_call(
                        trace_id,
                        step_number,
                        call_event_index,
                        tool_call,
                    )
                    # 输出到终端
                    if on_tool_event:
                        on_tool_event(
                            "call",
                            tool_call.name,
                            tool_call.arguments or {"raw": tool_call.raw_arguments},
                        )
                    # 重复调用检验，若重复调用达到阈值就不去执行而是返回一个错误给llm
                    if repeat_guard.should_block(tool_call):
                        result = ToolResult(
                            success=False,
                            content={},
                            error_code="REPEATED_TOOL_CALL",
                            error_message="相同工具和参数已连续调用过多次",
                        )
                    else:
                        # 真正调用tool
                        result = self.tool_registry.execute(
                            tool_call,
                            # 对于todo工具不信任模型传来的 Session ID，而是使用 Runtime 提供的context.session_id
                            # 目的时防止模型无法跨 Session 操作todo
                            ToolRuntimeContext(
                                user_id=owner,
                                session_id=current_session_id,
                                trace_id=trace_id,
                            ),
                        )

                    # 保存信息，例如tool输出结果到message，trace内容
                    self.message_repo.add_tool_result(
                        owner,
                        current_session_id,
                        tool_call.id,
                        result.to_message_content(),
                    )
                    self.trace_recorder.record_tool_result(
                        trace_id,
                        step_number,
                        call_event_index + 1,
                        tool_call.name,
                        result,
                    )
                    if on_tool_event:
                        on_tool_event(
                            "result",
                            tool_call.name,
                            {
                                "success": result.success,
                                "error_code": result.error_code,
                            },
                        )

            answer = "任务执行步骤超过限制，已停止。请拆分任务或补充更明确的信息。"
            self.trace_recorder.record_event(
                trace_id,
                step_number=self.config.max_steps,
                event_index=999,
                event_type="max_steps",
                status="failed",
                error_code="MAX_STEPS_EXCEEDED",
                error_message=answer,
            )
            self.trace_recorder.fail(
                trace_id,
                status="max_steps_exceeded",
                steps=self.config.max_steps,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                error_code="MAX_STEPS_EXCEEDED",
                error_message=answer,
            )
            return AgentResult(
                status="max_steps_exceeded",
                answer=answer,
                trace_id=trace_id,
                steps=self.config.max_steps,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
            )
        except KeyboardInterrupt:
            repaired_ids = self.message_repo.repair_pending_tool_calls(
                owner,
                current_session_id,
            )
            self.trace_recorder.record_event(
                trace_id,
                step_number=completed_steps,
                event_index=999,
                event_type="interrupted",
                status="failed",
                output_data={"repaired_tool_call_ids": repaired_ids},
                error_code="INTERRUPTED",
                error_message="Agent execution interrupted",
            )
            self.trace_recorder.fail(
                trace_id,
                status="interrupted",
                steps=completed_steps,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                error_code="INTERRUPTED",
                error_message="Agent execution interrupted",
            )
            raise
        except AgentError as exc:
            self._record_failure_event(
                trace_id,
                completed_steps,
                exc.code,
                exc.internal_message,
            )
            self.trace_recorder.fail(
                trace_id,
                status=exc.status,
                steps=completed_steps,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                error_code=exc.code,
                error_message=exc.internal_message,
            )
            return AgentResult(
                status=exc.status,
                answer=f"{exc.user_message} Trace ID: {trace_id}",
                trace_id=trace_id,
                steps=completed_steps,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
            )
        except Exception as exc:
            internal_message = f"{type(exc).__name__}: {exc}"
            self._record_failure_event(
                trace_id,
                completed_steps,
                "INTERNAL_ERROR",
                internal_message,
            )
            self.trace_recorder.fail(
                trace_id,
                status="internal_error",
                steps=completed_steps,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
                error_code="INTERNAL_ERROR",
                error_message=internal_message,
            )
            return AgentResult(
                status="internal_error",
                answer=f"运行时发生未预期错误，请查看 Trace 日志。Trace ID: {trace_id}",
                trace_id=trace_id,
                steps=completed_steps,
                prompt_tokens=total_prompt_tokens,
                completion_tokens=total_completion_tokens,
            )
        finally:
            with suppress(Exception):
                self.session_service.set_status(owner, current_session_id, "idle")

    def _record_failure_event(
        self,
        trace_id: str,
        step_number: int,
        error_code: str,
        error_message: str,
    ) -> None:
        with suppress(Exception):
            self.trace_recorder.record_event(
                trace_id,
                step_number=max(0, step_number),
                event_index=999,
                event_type="runtime_error",
                status="failed",
                error_code=error_code,
                error_message=error_message,
            )

    @staticmethod
    def _validate_input(user_id: str, session_id: str, user_input: str) -> None:
        if not isinstance(user_id, str) or not user_id.strip():
            raise InvalidUserInputError("user_id is empty")
        if not isinstance(session_id, str) or not session_id.strip():
            raise InvalidUserInputError("session_id is empty")
        if not isinstance(user_input, str) or not user_input.strip():
            raise InvalidUserInputError("user_input is empty")
