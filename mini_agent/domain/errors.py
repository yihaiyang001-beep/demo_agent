"""Stable error codes shared by runtime adapters."""

from __future__ import annotations


class AgentError(Exception):
    code = "AGENT_ERROR"
    status = "internal_error"
    default_user_message = "Agent 运行失败，请稍后重试。"

    def __init__(
        self,
        internal_message: str | None = None,
        *,
        user_message: str | None = None,
    ):
        self.internal_message = internal_message or self.code
        self.user_message = user_message or self.default_user_message
        super().__init__(self.internal_message)


class ConfigurationError(AgentError, ValueError):
    code = "CONFIGURATION_ERROR"
    default_user_message = "Agent 配置无效，请检查 AGENT_* 环境变量。"


class SessionNotFoundError(AgentError):
    code = "SESSION_NOT_FOUND"
    default_user_message = "未找到指定会话。"


class SessionAccessDeniedError(AgentError):
    code = "SESSION_ACCESS_DENIED"
    default_user_message = "无权访问指定会话。"


class InvalidUserInputError(AgentError, ValueError):
    code = "INVALID_USER_INPUT"
    default_user_message = "请输入有效的用户、会话和消息内容。"


class LLMUnavailableError(AgentError):
    code = "LLM_UNAVAILABLE"
    status = "llm_failed"
    default_user_message = "模型服务暂时不可用，请稍后重试。"


class LLMBadRequestError(AgentError):
    code = "LLM_BAD_REQUEST"
    status = "llm_failed"
    default_user_message = "模型请求无法处理，请检查模型和配置。"


class EmptyLLMResponseError(AgentError):
    code = "LLM_EMPTY_RESPONSE"
    status = "llm_failed"
    default_user_message = "模型返回了空响应，请重试。"


class ToolArgumentsParseError(AgentError):
    code = "INVALID_TOOL_ARGUMENTS"
    default_user_message = "工具参数不是合法的 JSON 对象。"


class ContextLimitExceededError(AgentError):
    code = "CONTEXT_LIMIT_EXCEEDED"
    default_user_message = "当前会话上下文过长，请压缩会话或开启新会话。"


class DatabaseOperationError(AgentError):
    code = "DATABASE_OPERATION_ERROR"
    default_user_message = "会话数据暂时无法保存，请稍后重试。"


class ToolExecutionError(AgentError):
    code = "TOOL_EXECUTION_ERROR"

    def __init__(self, code: str, user_message: str, internal_message: str | None = None):
        self.code = code
        super().__init__(internal_message or user_message, user_message=user_message)


class DuplicateToolError(AgentError):
    code = "DUPLICATE_TOOL"

    def __init__(self, tool_name: str):
        super().__init__(
            f"Tool is already registered: {tool_name}",
            user_message=f"工具名称重复：{tool_name}",
        )

