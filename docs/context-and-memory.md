# Context and Memory

## 四类状态

1. `messages`：当前 Session 的原始对话和 Tool Call/Result，永久保留。
2. `session_summaries`：早期历史的累计压缩表示。
3. `todos`：当前 Session 的结构化外部状态。
4. `traces` / `trace_steps`：Runtime 的可观察执行记录。

只有 System Prompt、摘要和本轮需要的完整消息组进入模型 Context。Todo、Trace、
异常堆栈和已被摘要覆盖的原始消息不会默认发送。

## 完整消息组

消息按用户轮次分组：

```text
user
assistant(tool_calls)
tool result(s)
assistant(tool_calls)
tool result(s)
assistant final
```

近期窗口只能增加或移除整个组，不能让 `tool` 消息失去前置 Assistant Tool Calls。

## 累计摘要

摘要记录 `summarized_until_message_id`。下一次压缩只处理该 ID 之后、近期窗口之前的
完整组，并将旧摘要与新历史一同交给无工具的 Summary 请求。成功后原子 upsert
摘要和边界；失败时旧摘要保持不变。

Todo Tool Call 的结构化内容和结果会从摘要输入中省略；可查询状态始终以 Todo 表为准。

## 阈值与降级

- `<70%`：摘要 + 未覆盖消息直接使用。
- `>=70%`：累计摘要早期组，然后重新估算。
- `>=90%`：保留更小的完整近期窗口。
- `>100%`：仅在发送副本中将长 Tool Result 替换为合法 JSON 截断说明。
- 仍超限：返回 `CONTEXT_LIMIT_EXCEEDED`，不发送非法请求。

压缩、窗口和截断从不更新或删除 `messages` 原文。

