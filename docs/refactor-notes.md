# Minimal Agent Runtime 重构基线

## 基线信息

- 建立日期：2026-07-29
- Python：3.13.9
- 基线标签：`corecoder-before-runtime-refactor`
- 开发分支：`refactor/minimal-agent-runtime`
- 原项目未包含 Git 元数据，本次先创建本地仓库并保存原始代码快照，再开始重构。
- 原测试在工作区临时目录下运行结果：85 passed，1 failed。
- 唯一基线失败为 `tests/test_core.py::test_config_defaults`：本地 `.env` 中的旧
  `CORECODER_MODEL` 会覆盖测试期望的默认模型。`.env` 已被 `.gitignore` 排除。

## 参考的 CoreCoder 设计

- OpenAI-compatible Chat Completions 消息格式。
- Assistant Tool Calls 与 Tool Result 的配对规则。
- 多轮 Agent Loop、最大轮次和中断后补齐 Tool Result 的工程经验。
- LLM 与工具接口分离、测试中替换 Fake LLM 的思路。

## 独立重写范围

以下模块在新的 `mini_agent/` 包中独立实现：

- Agent Runtime 与重复调用保护；
- `AGENT_*` 配置与 DeepSeek 非流式客户端；
- Tool Registry、Calculator、Weather、Todo 和 Mock Search；
- SQLite Repository、Session 隔离和历史恢复；
- Context 构建、消息分组、Token 估算和累计摘要；
- Trace 记录、异常映射和中断一致性修复；
- CLI、测试、文档和依赖组装。

## 隔离原则

- 新代码不继承或导入旧 `corecoder.agent.Agent`。
- 新工具系统不导入旧 `corecoder.tools.ALL_TOOLS`。
- SQLite 是新 Runtime 的唯一真实数据源。
- 旧 `corecoder/` 仅在迁移期间作为参考和基线保留。
- 只有新系统完成全量非 live 测试与最终检查后，才清理旧 Runtime 和旧测试。

## 完成状态

- 阶段 0–10 已按顺序通过专项测试并分别提交。
- 新 Runtime 默认测试、静态检查、ResourceWarning 检查和覆盖率均已通过。
- 旧 Runtime 已在最终阶段清理；原始快照仍可从
  `corecoder-before-runtime-refactor` 标签恢复。
