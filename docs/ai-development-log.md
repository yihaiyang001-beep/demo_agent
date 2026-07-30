# AI Prompt 与问题解决记录

> 项目：Mini Agent Runtime  
> 目标：记录本项目中 AI 的使用方式、关键 Prompt、本人做出的技术判断，以及开发过程中具有代表性的问题解决过程。

---

## 一、文档说明

本项目使用 AI 辅助完成需求梳理、架构讨论、开发计划生成、阶段性编码、代码审查和问题排查，但没有将笔试题直接交给 AI 一次性生成完整项目。

整个协作过程遵循以下原则：

1. 先由我提出对问题的理解、目标和约束。
2. 在思路不明确时，让 AI 通过反问帮助我补充需求和比较方案。
3. AI 提供候选方案，我结合笔试要求、开发成本和可测试性做最终选择。
4. 架构确定后，先形成阶段化开发方案，再进入编码。
5. Codex 每次只实现一个阶段，当前阶段测试通过后才进入下一阶段。
6. 项目形成雏形后，再通过全局测试和人工体验发现问题。
7. AI 负责辅助分析和实现，最终技术决策、验收标准和提交结果由我确认。

AI 在本项目中主要承担四种角色：

- **需求分析助手**：帮助从用户视角补全使用流程和边界条件。
- **架构讨论对象**：帮助比较方案、拆分职责和发现架构风险。
- **编码助手**：按照已经确认的开发方案分阶段实现代码。
- **代码审查助手**：检查笔试要求覆盖度、测试完整性和潜在缺陷。

---

# 第一部分：AI Prompt 与协作开发过程

## 1. 第一阶段：从用户视角明确 Demo Agent 的需求

### 1.1 我的初始思考

在开始编码前，我没有直接讨论类、函数或数据库表，而是先站在用户使用产品的角度考虑：

- 这是一个通用 Demo Agent，不再是 CoreCoder 这样的 Coding Agent。
- 核心考察点是 Agent Loop、Session、Context、工具机制、异常保护和 Trace。
- 第一版应优先证明 Runtime 能力，而不是投入大量时间开发前端。
- 工具需要覆盖本地计算、真实网络请求、结构化状态和可控 Mock。
- 用户需要能够创建、查看、切换和恢复不同 Session。
- 不同 Session 的消息和 Todo 必须相互隔离。
- 程序退出并重新启动后，历史会话仍然能够恢复。

### 1.2 代表性 Prompt

```text
我正在完成一个最小可用 Agent Runtime 的笔试项目。

我目前的理解是，这个项目的重点不是复杂前端，而是 Agent Loop、
工具调用、Session 隔离、上下文压缩、异常处理和 Trace。

请先不要直接写代码，也不要直接替我确定方案。

请从最终用户使用产品的角度，帮助我梳理需求，并通过反问的方式和我一起明确：

1. 第一版使用 CLI 还是 Web 更合理；
2. 用户如何创建、查看、切换和恢复 Session；
3. Session 之间需要隔离哪些数据；
4. 至少实现哪些工具，才能覆盖不同类型的工具调用；
5. 哪些功能属于笔试必需，哪些属于后续增强；
6. 最终终端录屏应该能够展示哪些完整场景。

我的初步想法是：
- 第一版先使用 CLI；
- 实现 calculator、weather、todo 和 mock search；
- Todo 按 Session 隔离；
- 使用 SQLite 实现历史恢复；
- Web 页面最后再考虑。

请针对这些想法提出问题、风险和替代方案，不要立即进入代码实现。
```

### 1.3 AI 提出的建议

AI 主要提出了以下建议：

- 第一版优先完成 CLI，避免前端分散核心 Runtime 的开发精力。
- 工具选择 Calculator、Weather、Todo 和 Mock Search。
- Runtime 的入口从一开始就接收 `user_id + session_id`。
- Session 列表优先展示摘要，没有摘要时展示标题或第一条用户消息。
- Todo 作为结构化状态独立保存，不应该始终放入对话 Context。
- 录屏应覆盖直接回答、工具调用、多轮工具循环、Session 隔离、历史恢复、Context 压缩和 Trace。

### 1.4 我的判断与最终选择

我接受了 CLI 优先的方案，因为笔试没有要求必须实现 Web，而 CLI 已经足够证明 Runtime 的核心能力。

最终选择的四个工具分别覆盖不同场景：

| 工具       | 类型           | 选择原因                            |
| ---------- | -------------- | ----------------------------------- |
| Calculator | 本地计算工具   | 验证参数 Schema、参数校验和本地执行 |
| Weather    | 真实网络工具   | 验证真实外部 API 调用和网络异常     |
| Todo       | 结构化状态工具 | 验证 SQLite 持久化和 Session 隔离   |
| Search     | Mock 工具      | 验证工具注册、工具选择和稳定测试    |

Todo 最终按 Session 隔离。虽然实际产品中 Todo 也可以设计为用户级资源，但本次笔试强调不同窗口互不影响，因此 Session 级设计更符合要求。

---

## 2. 第二阶段：讨论 CoreCoder 与 Demo Agent 的架构差异

### 2.1 我的初始思考

在设计新架构前，我先学习了 CoreCoder 的实现，并形成了以下理解：

- Agent Loop 是 Runtime 的核心，但 Runtime 不只是一个循环。
- Runtime 还应包含工具执行、Context、Session、异常保护和 Trace。
- CoreCoder 的基本循环可以作为学习参考，但它主要面向代码任务。
- CoreCoder 的 Agent 类承担了较多职责。
- 新项目可以保留 Function Calling 的基本思想，但需要重新划分模块边界。
- 不能只替换几个工具后直接提交，需要重新实现核心 Agent Runtime。

### 2.2 代表性 Prompt

```text
我已经阅读并理解了 CoreCoder 的基本实现。

我目前对它的理解是：
- Agent.chat() 中包含了主要 Agent Loop；
- LLM 根据工具 Schema 返回 Tool Call；
- Runtime 执行工具并把结果重新放回 Messages；
- 循环在模型不再返回 Tool Call 时结束。

但是我要开发的不是 Coding Agent，而是一个通用 Demo Agent。

请先不要写代码，和我一起分析以下问题：

1. CoreCoder 的 Coding Agent 和通用 Demo Agent 在需求上有什么差异；
2. 哪些模块可以保留设计思路；
3. 哪些模块必须重写；
4. AgentRuntime、LLMClient、ToolRegistry、SessionService、
   ContextManager、TraceRecorder 应该分别负责什么；
5. Messages、Session Summary、Todo 和 Trace 应该如何区分；
6. 如何避免 Agent 类继续承担过多职责。

我目前没有完全确定模块边界。
请通过反问的方式帮助我做选择，并在每个方案中说明优缺点。
最终目标是和我一起敲定架构，而不是直接替我生成完整代码。
```

### 2.3 AI 提出的架构方案

```text
AgentRuntime
├── Agent Loop 和流程调度
├── 最大 Step 控制
├── 重复调用保护
└── 异常与中断处理

LLMClient
├── 调用 DeepSeek
├── 关闭 Thinking 和流式输出
└── 解析 Content、Tool Calls 和 Token Usage

ToolRegistry
├── 工具注册
├── Schema 导出
├── Pydantic 参数校验
└── 统一工具执行和错误返回

SessionService
├── Session 创建与恢复
├── 用户和 Session 隔离
└── Session 状态维护

ContextManager
├── Summary 和 Messages 召回
├── Context 组装和估算
└── 自动与手动压缩

TraceRecorder
├── 记录 Context 构建
├── 记录 LLM 决策
├── 记录工具调用和结果
└── 记录耗时、重试和异常

Repository
└── SQLite 数据访问
```

同时，AI 建议：

- 使用 SQLite 作为唯一持久化数据源。
- 第一版使用非流式调用，先稳定实现 Agent Loop。
- 使用 OpenAI-compatible Function Calling。
- 工具按模型返回顺序执行。
- 不保存完整 Chain of Thought，只记录可观察的决策和执行步骤。
- 删除 Bash、ReadFile、EditFile 等 Coding Agent 工具。

### 2.4 我的判断与最终选择

我选择“保留项目外壳和 SDK 接入方式，但重写核心 Runtime”，而不是简单修改原来的 `Agent.chat()`。

保留的设计思想：

- OpenAI-compatible SDK 接入方式。
- Function Calling 消息格式。
- Assistant Tool Call 与 Tool Result 的对应关系。
- 最大循环次数的保护思想。

重新实现的核心部分：

- AgentRuntime。
- LLMClient。
- ToolRegistry。
- Session 和 SQLite Repository。
- ContextManager。
- TraceRecorder。
- Calculator、Weather、Todo 和 Search 工具。

第一版关闭流式输出。因为流式与非流式不会改变 Agent Loop 的本质，但流式会增加文本分片、工具参数分片、中断恢复和测试的复杂度。对于最小可用 Runtime，先保证非流式流程稳定更合理。

---

## 3. 第三阶段：生成并确认阶段化开发方案

### 3.1 我的初始思考

架构确定后，我没有立即让 AI 开始编码，而是先要求生成详细的开发方案。

开发方案需要满足：

- 只阅读文档就知道每一步要完成什么。
- 每个阶段有明确目标和边界。
- 每个阶段只修改有限范围。
- 每个阶段都包含对应测试。
- 当前阶段测试不通过，不进入下一阶段。
- 最终测试能够覆盖笔试要求。
- 开发过程可以通过 Git Commit 清晰追踪。

### 3.2 代表性 Prompt

```text
我们已经确定了最小 Agent Runtime 的架构，请根据最终决策生成一份详细的 Markdown 开发方案。

最终目标是实现一个支持以下能力的可运行 Agent：

- 真实 DeepSeek LLM API；
- 直接回答和 Tool Calling；
- 多轮 Agent Loop；
- Calculator、Weather、Todo、Mock Search；
- ToolRegistry 和参数 Schema；
- user_id + session_id 隔离；
- SQLite 历史恢复；
- Context 自动压缩；
- 最大 Step 和重复工具调用保护；
- Trace 日志；
- CLI 创建、查看和切换 Session；
- 单元测试、集成测试和真实 API 测试。

请不要只给模块列表，而要按阶段编写。

每个阶段必须包含：

1. 阶段目标；
2. 前置条件；
3. 需要新增、修改和删除的文件；
4. 核心类和接口；
5. 关键数据结构；
6. 实现步骤；
7. 对应测试用例；
8. 阶段验收标准；
9. 失败时的排查方向；
10. 建议的 Git Commit。

规则：
- 当前阶段测试未通过，不允许进入下一阶段；
- 先实现 CLI 和 Runtime，Web 最后再考虑；
- SQLite 是唯一真实数据源；
- Context 压缩不能删除原始 Messages；
- Assistant Tool Call 和 Tool Result 不能被拆开；
- Todo 不进入摘要，需要时通过工具查询；
- 不保存完整 Chain of Thought，只保存可观察 Trace。
```

### 3.3 我对开发方案的调整

AI 生成初稿后，我重点检查了：

- 阶段之间是否存在错误依赖。
- 是否过早引入 Web 页面。
- Session 是否从第一版 Runtime 就接入。
- Context 压缩是否会删除或破坏原始消息。
- Trace 是否建立在基本 Agent Loop 之后。
- 测试是否能够与笔试要求对应。
- 是否存在一次性修改过多模块的问题。

最终确定的主要开发顺序：

```text
配置与项目骨架
→ 非流式 LLMClient
→ 工具抽象与 ToolRegistry
→ SQLite 与 Repository
→ Session 管理
→ Agent Runtime 基本循环
→ Trace
→ Context 压缩
→ CLI Session 命令
→ 单元测试和集成测试
→ 真实 API 测试
→ 文档与终端录屏
```

---

## 4. 第四阶段：让 Codex 按开发方案分阶段实现

### 4.1 我的使用原则

完成开发方案后，我使用 Codex 辅助编码，但没有要求它一次性生成完整项目。

每次只允许实现一个阶段，并要求：

- 先阅读开发方案和当前代码状态。
- 不提前实现后续阶段。
- 不修改当前阶段范围外的代码。
- 完成后运行当前阶段测试。
- 测试失败必须先定位和修复。
- 汇报修改文件、核心设计、测试结果和剩余风险。
- 当前阶段通过后才进入下一阶段。

### 4.2 通用阶段开发 Prompt

```text
请阅读项目中的《Agent Runtime 重构开发方案.md》。

现在只实现“阶段 X”，不要提前实现后续阶段。

执行要求：

1. 先检查当前项目状态和上一阶段测试结果；
2. 列出本阶段计划修改的文件；
3. 严格按照开发方案中的接口和数据结构实现；
4. 不要修改本阶段范围外的模块；
5. 保留清晰的类型注解和异常处理；
6. 完成后运行本阶段要求的全部测试；
7. 如果测试失败，先定位并修复，不能跳过；
8. 最后输出：
   - 修改了哪些文件；
   - 核心实现是什么；
   - 哪些测试通过；
   - 是否满足本阶段验收标准；
   - 仍然存在什么风险。

在我确认本阶段通过之前，不要进入下一阶段。
```

### 4.3 Agent Runtime 阶段 Prompt

```text
请只实现开发方案中的 Agent Runtime 基本循环。

我要求 Runtime 的入口为：

runtime.run(user_id, session_id, user_input)

执行顺序必须包括：

- 校验输入；
- 创建或恢复 Session；
- 保存用户 Message；
- 创建 Trace；
- 构建 Context；
- 调用非流式 LLM；
- 判断 Final Answer 或 Tool Calls；
- 保存 Assistant Tool Calls；
- 通过 ToolRegistry 顺序执行工具；
- 保存 role=tool 的结果；
- 继续下一次 LLM Step；
- 无 Tool Call 且 Content 不为空时结束；
- 最大 Step 后强制停止；
- finally 中恢复 Session 为 idle。

请不要把 SQL、具体工具逻辑或 Context 压缩代码写进 AgentRuntime。

完成后使用 ScriptedLLM 编写并运行以下集成测试：

- 直接回答；
- 单工具调用；
- Weather → Todo 多轮调用；
- 一次返回多个工具时按顺序执行；
- 达到最大 Step；
- 第三次重复 Tool Call 被阻止。
```

### 4.4 我的判断

阶段化开发主要用于避免：

- AI 一次性生成大量代码，导致模块边界不一致。
- 后续接口与前面阶段发生冲突。
- 测试全部堆到开发末期。
- 出现错误后难以判断由哪个阶段引入。
- 为了快速完成任务而跳过异常和边界处理。

每个阶段通过对应测试后再继续，能够让代码状态始终保持可运行，也方便我逐步阅读和理解实现。

---

## 5. 第五阶段：全局测试、真实体验和代码微调

### 5.1 我的初始思考

项目形成雏形后，我从两个角度继续检查：

1. 自动化测试是否真正覆盖笔试要求。
2. 真实用户使用过程中是否存在语义、交互和异常问题。

### 5.2 全局代码审查 Prompt

```text
项目已经开发完成，请不要只检查代码是否能够运行。

请按照笔试要求进行完整代码审查，逐项检查：

1. Agent Loop 是否支持直接回答、工具调用、继续循环和最终结束；
2. ToolRegistry 是否真正根据名称、描述和参数 Schema 工作；
3. Session 是否使用 user_id + session_id 隔离；
4. 程序重启后是否能够恢复 Messages、Summary 和 Todo；
5. Context 压缩是否保留原始消息；
6. Tool Call 和 Tool Result 是否可能被裁剪拆开；
7. 最大 Step 和重复 Tool Call 是否真的能阻止死循环；
8. 工具、LLM、数据库异常是否会留下不一致状态；
9. Trace 是否足够还原执行过程；
10. 测试文件是否可以与笔试要求逐项对应；
11. 是否存在 API Key、数据库或缓存文件误提交风险。

请对每一项给出：
- 符合；
- 部分符合；
- 不符合；
- 证据代码位置；
- 需要修正的问题。

最后实际运行测试，而不是只做静态判断。
```

### 5.3 真实体验与微调 Prompt

```text
请从最终用户实际使用 CLI 的角度检查当前项目。

重点观察：
- 命令名称和输出含义是否容易理解；
- Session 创建、切换和恢复是否符合直觉；
- 工具调用结果是否能被用户确认；
- Context 压缩前后是否能直观看出变化；
- Trace 是否足以解释一次请求经历了哪些步骤；
- 网络错误、参数错误和空响应是否给出明确提示。

发现问题后，请先描述实际现象和根因，
再给出最小修改方案与对应测试，不要直接进行大范围重构。
```

### 5.4 最终验证方式

#### 单元测试

验证：

- LLM 输出与 Tool Call 解析。
- ToolRegistry 和参数校验。
- Calculator、Weather、Todo、Search。
- SQLite Repository。
- SessionService。
- Context 压缩和消息分组。
- RepetitionGuard。
- TraceRecorder。

#### 集成测试

验证：

- LLM 直接回答。
- 单工具调用。
- 多轮工具调用。
- Session 隔离。
- 程序重启恢复。
- Context 压缩后继续对话。
- Runtime 异常处理。
- 中断后的消息修复。

#### Live 测试

验证：

- 真实 DeepSeek API。
- 真实 Open-Meteo API。
- LLM 自主调用 Calculator。
- Weather → Todo 多轮执行。
- 真实上下文追问。

#### 人工终端体验

验证：

- `/new`
- `/sessions`
- `/switch`
- `/current`
- `/todos`
- `/trace`
- `/tokens`
- `/compact`
- `/exit`

---

# 第二部分：问题解决纪要

## 6. 问题记录格式

为便于回顾和评审，所有问题统一按照以下结构记录：

```text
问题背景与现象
→ 根因分析
→ 关键 AI/Codex Prompt
→ AI/Codex 建议
→ 我的判断与取舍
→ 最终实现方案
→ 验证方式与结果
→ 最终结论
```

记录重点不是展示 AI 生成了多少代码，而是展示：

- 问题是如何被发现的。
- AI 提供了哪些候选方案。
- 哪些方案被采用或放弃。
- 最终实现为什么符合项目要求。
- 解决结果如何通过测试或真实运行验证。

---

## 7. 问题一：Weather Tool 中文城市名称兼容性

**状态：已解决**

### 7.1 问题背景与现象

天气工具最初直接将用户输入的城市名称传给 Open-Meteo Geocoding API。

当用户查询：

```text
宜春
江西省宜春市
```

Open-Meteo 返回 HTTP 200 和合法 JSON，但响应中没有 `results` 字段：

```json
{
  "generationtime_ms": 0.1
}
```

原实现将这种情况错误归类为 `WEATHER_RESPONSE_INVALID`，最终显示“地理编码响应格式无效”。

改用拼音 `Yichun` 查询时可以获得结果，但候选中同时可能包含：

- 江西省宜春市。
- 黑龙江省伊春市。
- 宜春明月山机场。
- 其他名称相似地点。

因此，仅将中文转换为拼音并选择第一个候选，仍然存在定位错误风险。

### 7.2 根因分析

1. Open-Meteo 对部分中文城市名称的索引支持不完整。
2. 地理编码无匹配结果时，API 可能省略 `results`，而不是返回空数组。
3. 中文转拼音后可能产生同音城市，例如“宜春”和“伊春”都对应 `Yichun`。
4. 候选结果可能包含机场等非城市地点，不能简单选择第一个结果。
5. Open-Meteo 的每日 `weather_code` 表示当天较严重的预报天气，不等同于全天持续天气或当地气象站现场观测。

### 7.3 关键 AI/Codex Prompt

```text
Weather Tool 查询“江西省宜春市”时，Open-Meteo Geocoding API 返回 HTTP 200，
但没有 results 字段；查询 Yichun 时又会返回宜春、伊春和机场等多个候选。

请不要只增加一个简单拼音转换。

请分析并实现：
1. 如何区分“无搜索结果”和“响应格式错误”；
2. 如何从完整行政区划名称中提取城市名称；
3. 如何在中文查询失败后回退到拼音；
4. 如何使用省份、城市类型和候选字段完成同名城市消歧；
5. 如何避免优先选择机场等非城市地点；
6. 如何通过单元测试和 Live 测试证明定位结果正确。

完成后说明采用了哪些匹配规则，以及仍然存在什么边界。
```

### 7.4 AI/Codex 建议

Codex 建议采用分阶段回退和候选评分：

```text
原始名称
→ 提取行政区划中的城市名称
→ 转换为拼音
→ 查询多个候选
→ 根据行政区划和地点类型消歧
```

同时建议将缺少 `results` 的响应视为“当前查询无匹配结果”，继续尝试下一候选，而不是立即报响应格式错误。

### 7.5 我的判断与取舍

我没有采用“拼音查询后直接选择第一个结果”的简单方案，因为它无法解决宜春和伊春同音、机场混入候选等问题。

最终要求实现：

- 中文原名优先。
- 中文失败后再回退拼音。
- 使用省级行政区划参与匹配。
- 优先行政中心和人口聚居地。
- 降低机场等非城市候选优先级。
- 返回实际命中的地区和坐标，便于确认结果。

### 7.6 最终实现方案

- 引入 `pypinyin`，为中文城市生成拼音候选。
- 支持从“江西省宜春市”等完整名称中提取“宜春”。
- 将缺少 `results` 的响应视为当前候选无匹配。
- 所有候选均无结果时返回 `CITY_NOT_FOUND`。
- 将候选数量增加到 10，用于同名城市消歧。
- 使用原始名称中的省、市信息匹配 `admin1`、`admin2`。
- 优先选择 `PPLC`、`PPLA`、`PPLA2`、`PPL` 等人口聚居地。
- 降低机场等非城市地点的选择优先级。
- 返回城市、地区、国家、纬度和经度。

天气结果还增加了语义说明：

```json
{
  "weather_scope": "daily_most_severe_forecast",
  "weather_note": "全天较严重天气预报，不代表全天持续或现场实况",
  "data_type": "numerical_weather_prediction"
}
```

### 7.7 验证方式与结果

真实查询：

```text
江西省宜春市
```

最终定位：

```text
城市：宜春市
地区：江西
纬度：27.83333
经度：114.4
```

验证结果：

- 未匹配到黑龙江省伊春市。
- 未匹配到宜春明月山机场。
- 中文完整城市名称可自动完成拼音回退。
- 地理编码和天气预报调用链正常。
- Weather 专项单元测试通过。
- Open-Meteo 中文城市 Live 测试通过。
- 当时项目完整测试结果为 `118 passed, 6 skipped`。

### 7.8 最终结论

问题不只是“中文无法搜索”，还涉及无结果响应识别、拼音回退、同音城市消歧和地点类型筛选。

最终方案保证用户可以直接输入中文行政区划名称，并尽可能选择正确城市，而不需要手动改成拼音。

---

## 8. 问题二：Context 压缩可能拆开 Tool Calling 消息链

**状态：已解决**

### 8.1 问题背景与现象

Context 过长时，需要保留近期消息并将较早历史压缩成 Session Summary。

但是 Tool Calling 消息存在严格关联：

```text
assistant（包含 tool_calls）
→ tool（包含对应 tool_call_id）
```

如果直接按消息数量截取最近若干条，可能出现：

- 保留了 Tool Result，却删除了对应的 Assistant Tool Call。
- 保留了 Assistant Tool Call，却删除了部分 Tool Result。
- 下一次发送给 LLM 的消息结构不完整。
- API 拒绝请求，或模型无法理解工具结果来源。

### 8.2 根因分析

问题的根因是把 Message 当作彼此独立的记录处理，而忽略了 Tool Calling 消息之间的结构关系。

同时还存在两个风险：

1. 如果压缩后删除原始 Messages，将无法完整恢复历史和排查问题。
2. 如果每次摘要都重新处理全部历史，会重复总结相同消息，并不断增加摘要噪声。

### 8.3 关键 AI/Codex Prompt

```text
Agent 的 Context 达到长度限制后，需要保留最近消息并压缩较早历史。

但是消息中包含 assistant tool_calls 和对应的 tool results。
如果直接按照最近 N 条消息截断，可能拆开工具调用链。

请分析并实现：

1. 哪些消息必须作为不可拆分的完整消息组；
2. 如何在压缩边界处保证工具调用链完整；
3. 原始 Messages 是否应该删除；
4. Session Summary 如何进行增量更新，避免重复摘要；
5. 压缩失败时如何保持旧 Summary 可用；
6. Todo 等结构化状态是否应该进入 Summary；
7. 需要哪些单元测试和集成测试。

请先说明数据不变量，再给出最小实现方案。
```

### 8.4 AI/Codex 建议

AI 建议：

- 将普通单条消息作为一个组。
- 将包含 Tool Calls 的 Assistant Message 与其后对应的 Tool Results 作为一个不可拆分的组。
- 原始 Messages 永久保存在 SQLite。
- Summary 只作为构建 Context 时的压缩表示。
- 使用摘要边界记录已经压缩到哪一条 Message。
- 新 Summary 由“旧 Summary + 新增待压缩消息”生成。
- Todo 不进入 Summary，需要时通过 Todo Tool 查询。

### 8.5 我的判断与取舍

我接受了“消息分组 + 增量摘要”方案。

我没有采用以下方案：

- **直接删除旧 Messages**：会破坏历史恢复和问题排查。
- **固定保留最近 N 条数据库消息**：可能拆开 Tool Calling 链。
- **把 Todo 全量写入 Summary**：Todo 是结构化状态，可能变化，不应与自然语言摘要混在一起。

### 8.6 最终实现方案

Context 构建流程：

```text
读取旧 Session Summary
→ 读取摘要边界后的 Messages
→ 按 Tool Calling 关系构建完整消息组
→ 根据阈值选择需要摘要的完整消息组
→ 调用 LLM 生成新 Summary
→ 保存 Summary 和新的摘要边界
→ 使用 Summary + 近期完整消息组构建下一次 Context
```

压缩规则：

- 达到约 70% 阈值时，压缩较早历史。
- 达到约 90% 阈值时，进一步缩小近期消息窗口。
- 原始 Messages 始终保留在 SQLite。
- 摘要生成失败时继续使用旧 Summary，不破坏当前 Session。
- 长 Tool Result 只在构建 Context 时截断，不修改数据库原始内容。

### 8.7 验证方式与结果

通过测试验证：

- 低于阈值时不触发压缩。
- 达到阈值时生成 Summary。
- 原始 Messages 数量和内容不变。
- Summary 边界正确更新。
- 已摘要消息不会被重复摘要。
- Assistant Tool Call 和 Tool Results 不会被拆开。
- 长 Tool Result 的 Context 版本可以截断，数据库原文仍保留。
- 摘要失败时旧 Summary 继续可用。
- 压缩后 Agent 仍能继续完成工具追问。

相关测试包括：

```text
tests/unit/context/test_context_manager.py
tests/unit/context/test_message_groups.py
tests/integration/test_context_compression.py
```

### 8.8 最终结论

Context 压缩不是简单删除旧消息，而是需要维护 Tool Calling 消息结构、摘要边界和原始数据完整性。

最终方案实现了：

```text
原始历史可恢复
+ Context 大小可控制
+ Tool Calling 结构合法
+ Summary 可增量更新
```

---

## 9. 问题三：程序中断后存在悬空 Tool Call 和 Busy Session

**状态：已解决**

### 9.1 问题背景与现象

Agent 执行过程中，Assistant Tool Call 会先保存到 Messages，然后 Runtime 执行工具并保存 Tool Result。

如果程序恰好在两者之间发生中断，例如：

- 用户按下 `Ctrl+C`。
- 进程异常退出。
- 网络或数据库操作中断。
- 上一次运行留下 `busy` 状态。

数据库中可能留下：

```text
assistant tool_call
→ 缺少对应的 tool result
```

同时 Session 可能一直保持 `busy`。

下次恢复该 Session 时，如果直接将这段历史发送给 LLM，消息结构可能不合法；如果 Session 一直处于 busy，也可能影响继续执行。

### 9.2 根因分析

Agent Loop 中的数据库写入和外部工具执行无法被一个简单数据库事务完全包裹：

- Tool Call 已经持久化。
- 外部工具可能尚未执行完成。
- 进程可能在任意位置退出。
- `finally` 在强制结束进程时不一定有机会执行。

因此不能只依赖正常流程中的状态回收，还需要在恢复 Session 时主动检查并修复历史。

### 9.3 关键 AI/Codex Prompt

```text
当前 Runtime 会先保存 assistant tool_calls，再执行工具并保存 role=tool 结果。

如果程序在两步之间被 Ctrl+C 中断，数据库会留下没有 Tool Result 的 Tool Call，
Session 也可能保持 busy。

请设计一个可恢复方案，要求：

1. 程序重启或继续同一 Session 时能够识别悬空 Tool Call；
2. 为缺失结果补充 API 合法的 tool message；
3. 不重复补充已经存在的 Tool Result；
4. 不在恢复阶段重新执行可能具有副作用的工具；
5. stale busy Session 能够恢复为可执行状态；
6. 正常异常处理仍需在 finally 中设置 idle；
7. 增加单元测试和集成测试验证 Ctrl+C 与重启恢复。

请说明为什么不能简单重新执行未完成工具。
```

### 9.4 AI/Codex 建议

AI 建议在每次继续 Session 前增加历史修复步骤：

- 检查 Assistant Tool Calls 是否都有对应 `tool_call_id` 的 Tool Result。
- 对缺失结果补写一个结构化失败 Tool Message。
- 明确标记该调用因上次运行中断而未完成。
- 不自动重新执行工具，避免 Todo Add 等带副作用操作重复执行。
- 对已经存在结果的调用不做任何修改。
- 检测到旧的 Busy Session 时恢复为 Idle。
- 当前 Runtime 正常结束或异常时仍在 `finally` 中设置 Idle。

### 9.5 我的判断与取舍

我没有选择“恢复后自动重跑缺失工具”。

原因是部分工具具有副作用，例如：

```text
todo action=add
```

如果工具实际上已经执行成功，但程序在保存 Tool Result 前退出，自动重跑会创建重复 Todo。

因此更安全的做法是：

- 保证消息结构合法。
- 明确告诉 LLM 上次调用未确认完成。
- 由模型根据当前上下文决定重新询问、重试或换一种方式。
- 不在恢复逻辑中擅自重复副作用操作。

### 9.6 最终实现方案

恢复流程：

```text
读取当前 Session 历史
→ 查找缺少 Tool Result 的 Assistant Tool Call
→ 检查对应 tool_call_id 是否已有结果
→ 对缺失项补写中断错误 Tool Message
→ 修复 stale busy 状态
→ 再构建 Context 并继续 Agent Loop
```

正常运行过程中：

```text
Session 设置为 busy
→ 执行 Agent Loop
→ 成功或异常
→ finally 中设置为 idle
```

### 9.7 验证方式与结果

通过测试验证：

- 缺失 Tool Result 时能够补写失败结果。
- 已有 Tool Result 时不会重复插入。
- 修复后的历史符合 Tool Calling 消息结构。
- 修复后可以继续调用 LLM。
- `Ctrl+C` 中断后当前 Tool Call 可以被修复。
- 程序重启后 stale busy Session 可以恢复。
- 正常异常路径会将 Session 恢复为 idle。

相关测试包括：

```text
tests/unit/storage/test_interruption_repair.py
tests/integration/test_interruption_recovery.py
```

### 9.8 最终结论

中断恢复的重点不是保证外部工具“恰好执行一次”，而是在缺少分布式事务的情况下：

- 避免重复副作用。
- 保证消息结构合法。
- 保持 Session 可继续使用。
- 让失败状态对 LLM 和 Trace 可见。

---

## 10. 问题四：模型重复调用相同无效工具导致 Agent 死循环

**状态：已解决**

### 10.1 问题背景与现象

当工具返回错误时，模型可能没有修正原来的假设，而是继续使用完全相同的工具和参数重复调用。

例如：

```text
weather {"city": "不存在的城市", "date": "today"}
→ CITY_NOT_FOUND
→ 模型再次调用相同参数
→ 再次失败
```

即使 Runtime 存在最大 8 Step 限制，这种行为仍会：

- 浪费 LLM Token 和外部 API 请求。
- 延长用户等待时间。
- 让 Trace 中充满没有价值的重复步骤。
- 最终只依赖最大 Step 被动结束。

### 10.2 根因分析

最大 Step 只能限制整个循环长度，不能识别“模型正在重复同一个错误”。

需要额外判断：

```text
工具名称是否相同
+ 参数语义是否相同
+ 是否连续重复失败
```

同时，参数 JSON 的键顺序可能不同，因此不能直接比较原始字符串。

### 10.3 关键 AI/Codex Prompt

```text
Agent 已有 max_steps=8，但模型在工具返回错误后，
可能连续调用相同工具和相同参数，直到达到最大 Step。

请设计一个最小 RepetitionGuard，要求：

1. 使用 tool name + 规范化 arguments 生成指纹；
2. JSON 键顺序不同但语义相同时，应视为相同调用；
3. 不同工具或不同参数应重置连续计数；
4. 成功调用后重置错误重复状态；
5. 前两次允许模型尝试，第三次阻止真实工具执行；
6. 将结构化错误返回给 LLM，让模型重新评估；
7. 仍然保留 max_steps 作为最终保险；
8. Trace 中应能看到重复调用被阻止。

请补充单元测试和 Agent Loop 集成测试。
```

### 10.4 AI/Codex 建议

AI 建议为每次 Runtime 请求创建独立 RepetitionGuard：

- 将工具名称和规范化 JSON 参数组合为指纹。
- 相同错误指纹连续出现时增加计数。
- 达到阈值后不再执行真实工具。
- 返回结构化错误结果，提示模型重新评估假设。
- 调用成功后重置 Guard。
- 最大 Step 继续作为通用兜底。

### 10.5 我的判断与取舍

我没有选择第一次重复就立即阻止，因为模型可能需要一次合理重试，例如短暂网络错误。

最终采用：

- 同一工具和参数允许有限次数尝试。
- 第三次相同调用被阻止。
- Guard 只在当前用户请求的 Agent Loop 内生效。
- 不跨请求永久保存重复状态。
- 最大 Step 和 RepetitionGuard 同时保留。

两者职责不同：

| 保护机制        | 解决的问题                        |
| --------------- | --------------------------------- |
| RepetitionGuard | 识别连续重复的同一错误操作        |
| Max Steps       | 限制任何原因造成的过长 Agent Loop |

### 10.6 最终实现方案

```text
接收 Tool Call
→ 规范化 arguments
→ 生成 tool name + arguments 指纹
→ 与上次失败指纹比较
→ 未达到阈值：执行工具
→ 达到阈值：跳过执行并返回结构化错误
→ 成功执行后重置 Guard
```

阻止后的结果仍作为 `role=tool` 写回 Messages，让 LLM 有机会：

- 修改参数。
- 选择其他工具。
- 根据已有证据直接回答。
- 明确向用户说明无法完成。

### 10.7 验证方式与结果

通过测试验证：

- JSON 键顺序不影响调用指纹。
- 相同工具和参数会累积重复计数。
- 不同工具或不同参数不会被误判。
- 第三次相同调用被阻止。
- 被阻止后真实工具不会再次执行。
- 错误结果能够回传 LLM。
- 成功调用后 Guard 会重置。
- 达到最大 Step 时仍能强制终止。

相关测试包括：

```text
tests/unit/test_repetition_guard.py
tests/integration/test_agent_loop.py
```

### 10.8 最终结论

RepetitionGuard 不是替代最大 Step，而是更早识别没有进展的重复失败。

最终形成双重保护：

```text
重复错误保护
+ 最大步骤保护
```

既减少无效调用，也保证任何情况下 Agent Loop 都有明确上限。

---

# 第三部分：AI 使用总结

## 11. 最终协作流程

本项目没有采用“复制题目给 AI，然后一次性生成完整代码”的方式，而是按照软件工程流程分阶段协作：

```text
本人提出初步理解和约束
→ AI 通过反问帮助澄清需求
→ 本人比较方案并做出选择
→ AI 协助整理阶段化开发文档
→ Codex 按文档逐阶段编码
→ 每阶段测试通过后继续
→ 本人通过全局测试和真实体验发现问题
→ AI/Codex 协助分析和实现修复
→ 本人检查代码、测试和演示结果
→ 完成最终提交
```

## 12. 由我确认的关键决策

AI 提高了架构讨论、遗漏检查、编码和测试效率，但以下关键决策由我确认：

- 第一版使用 CLI，而不是优先开发 Web。
- 将项目从 Coding Agent 改为通用 Demo Agent。
- 删除原有 Coding Tools，重新实现四类工具。
- 保留 Function Calling 思想，但重写核心 Runtime。
- 使用 `user_id + session_id` 进行会话隔离。
- Todo 按 Session 保存。
- SQLite 作为唯一持久化数据源。
- 第一版使用非流式 LLM 调用。
- 工具按模型返回顺序执行。
- Context 使用 Session Summary 加近期完整消息组。
- 原始 Messages 不因压缩而删除。
- Todo 不进入 Session Summary。
- 不保存完整 Chain of Thought，只保存可观察 Trace。
- 使用 RepetitionGuard 和 Max Steps 双重限制循环。
- 中断恢复时不自动重跑可能具有副作用的工具。
- 使用单元测试、集成测试、Live 测试和人工终端体验共同验收。

## 13. 对 AI 辅助开发的理解

我认为合理使用 AI 的关键不是让 AI 替代思考，而是：

1. 先明确问题和约束。
2. 让 AI 提供候选方案和风险提示。
3. 根据项目目标做出技术取舍。
4. 将决策固化为开发计划和测试标准。
5. 通过代码、测试和真实运行验证结果。

AI 的输出不是最终答案，而是开发过程中的输入之一。最终提交的架构、代码和文档，需要由开发者理解、判断并承担责任。