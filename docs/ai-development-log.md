# AI Development Log

本记录保留重构过程中的问题、提问方式、建议和人工判断，不记录模型私有思维链。

## 问题：Tool Call 参数解析失败

### Prompt

如何设计 OpenAI-compatible Tool Call 参数解析，使坏 JSON 不被静默转换为 `{}`，同时
不让一次格式错误破坏 Agent Loop？

### 建议与判断

保留 `raw_arguments`、解析结果和 `parse_error`；Registry 不执行坏参数，而是返回
`INVALID_TOOL_ARGUMENTS` Tool Result。采用该方案，不额外增加一次 JSON 修复 LLM
调用。

## 问题：SQLite Session 复合隔离

### Prompt

如何让同名 Session 可被不同用户使用，同时避免 CLI 切换和 Todo 越权？

### 建议与判断

所有表以 `user_id + session_id` 为边界，Session 使用复合主键；Todo 的所有者只能来自
`ToolRuntimeContext`，不进入模型 Schema。采用，并增加重启与同名 Session 测试。

## 问题：安全 Calculator

### Prompt

如何在不使用 `eval()` 的情况下支持基础算术，并限制拒绝服务风险？

### 建议与判断

使用 `ast.parse(mode="eval")` 和节点白名单，限制表达式长度、AST 节点、指数绝对值及
结果范围。采用；函数、属性、下标、字符串和变量全部拒绝。

## 问题：压缩不能拆断 Tool Call

### Prompt

如何截取近期消息而不产生孤立 `tool` 消息，并支持增量摘要？

### 建议与判断

以用户轮次构造 `MessageGroup`，窗口从尾部按完整组选择；摘要保存边界 ID，只处理新
历史。采用；原始消息不修改，摘要注入 System Prompt。

## 问题：Todo 为什么不进入摘要

### Prompt

如何避免摘要中的旧 Todo 与 SQLite 最新状态冲突？

### 建议与判断

Todo 作为独立结构化状态按需查询；摘要输入省略 Todo Tool Call/Result，并脱敏关联的
Todo content。采用，SQLite 是唯一真实来源。

## 问题：工具中断后的历史一致性

### Prompt

进程在 Assistant Tool Calls 后、Tool Result 前中断时，下一次请求如何恢复？

### 建议与判断

每轮开始前扫描缺失 call ID，补写结构化 `INTERRUPTED`；Ctrl+C 立即修复；Session 使用
`busy/idle`，启动恢复遗留 busy。采用，并确保已有结果不重复。

## 问题：Retry 与 Trace

### Prompt

如何只重试瞬态 LLM 错误，同时让 Retry 可观察且不泄露密钥？

### 建议与判断

限流、超时、连接和 5xx 使用 1/2 秒退避；认证、模型、Schema 和 4xx 不重试。
Trace 只记错误类别、次数和等待时长；API Key 和敏感字段递归脱敏。采用。

## 问题：SQLite 连接生命周期

### 现象

覆盖率运行出现大量未关闭连接 ResourceWarning。标准 SQLite `with connection` 只负责
事务，不自动关闭句柄。

### 最终实现

使用 `ManagedConnection`，在 `__exit__` 完成提交/回滚后关闭连接，并用
`ResourceWarning` 作为错误运行全量测试验证。

