# Agent Runtime 测试矩阵

默认测试命令不会访问真实 LLM 或真实网络：

```bash
pytest -q
pytest tests/unit -q
pytest tests/integration -q
ruff check .
```

Live 测试仅在显式设置 `RUN_LIVE_TESTS=1`，且需要模型的用例同时存在
`AGENT_API_KEY` 时运行：

```bash
pytest tests/live -m live -s
```

## 核心场景映射

| 编号 | 场景 | 自动化证据 |
|---|---|---|
| T01 | 普通问候直接回答 | `tests/integration/test_agent_loop.py::test_direct_answer` |
| T02 | Calculator 自主调用 | `tests/integration/test_agent_loop.py::test_single_tool_call` |
| T03 | 北京真实天气 | `tests/live/test_end_to_end.py::test_live_weather_tool` |
| T04 | Mock Search 标识 | `tests/unit/tools/test_search.py` |
| T05 | 添加 Todo | `tests/unit/tools/test_todo.py::test_todo_add_and_list` |
| T06 | 查看 Todo | `tests/unit/tools/test_todo.py::test_todo_add_and_list` |
| T07 | 多轮工具 Loop | `tests/integration/test_agent_loop.py::test_multi_round_tools` |
| T08 | 压缩后工具追问 | `tests/integration/test_context_compression.py` |
| T09 | 两个 Session 隔离 | `tests/integration/test_session_recovery.py` |
| T10 | 重启恢复 | `tests/integration/test_session_recovery.py` |
| T11 | `/sessions` 预览 | `tests/unit/storage/test_session_service.py`、`tests/unit/test_cli_sessions.py` |
| T12 | 自动 Context 压缩 | `tests/unit/context/test_context_manager.py` |
| T13 | 压缩后关键事实 | `tests/unit/context/test_context_manager.py::test_summary_is_injected_into_system_context` |
| T14 | 工具参数错误 | `tests/integration/test_runtime_errors.py::test_invalid_tool_args_is_returned_to_llm` |
| T15 | Weather 超时 | `tests/unit/tools/test_weather.py::test_weather_timeout` |
| T16 | 重复 Tool Call | `tests/integration/test_agent_loop.py::test_third_repeated_tool_call_is_returned_as_error` |
| T17 | 无限 Loop / 最大 Step | `tests/integration/test_agent_loop.py::test_max_steps` |
| T18 | LLM 超时和重试 | `tests/unit/test_llm_client.py::test_retry_on_timeout`、`tests/integration/test_runtime_errors.py::test_llm_timeout_after_retries_returns_trace_id` |
| T19 | 工具执行中断 | `tests/integration/test_interruption_recovery.py` |
| T20 | Trace 还原执行 | `tests/unit/test_trace_recorder.py`、`tests/integration/test_runtime_errors.py` |

## 分层约束

- Unit：不访问真实 LLM 或网络；SQLite 使用测试临时目录。
- Integration：使用临时 SQLite 和 `ScriptedLLM`，验证完整模块协作。
- Live：真实 DeepSeek/Open-Meteo，默认跳过，避免普通测试受费用和网络波动影响。
- Tool Call 参数解析失败必须保留原始字符串和错误，不允许静默转换为 `{}`。
- 压缩测试必须断言原始消息数量和内容保持不变。
- Todo、消息、摘要和 Trace 的所有访问都包含 `user_id + session_id` 所有者边界。

