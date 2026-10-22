# ERP-AGENT 源码学习路线图

> 目标：理解项目原理与架构。有 Python 基础。
> 学习方式：按模块读源码。共 10 个模块。

## 模块速查表

| 模块 | 主题 | 核心代码 | 学完能回答 |
|---|---|---|---|
| 0 | 整体架构与启动流程 | `web_main.py` `chat.py` `agent_loader.py` | 一条请求从浏览器到 ERP 的完整旅程 |
| 1 | Agent Core 组装 | `main_agent.py` | 一个 Agent 是怎么被一步步"拼"出来的 |
| 2 | Harness 四阶段工作流 | `harness.py` `harness_config.yaml` | Planning→Executing→Review→Result 状态机 |
| 3 | 12 个中间件栈 | `middlewares/*.py` | 中间件如何层层包裹每轮模型调用 |
| 4 | 35 个工具系统 | `tools/*.py` | MCP + 自定义 + 记忆工具是怎么注册的 |
| 5 | MCP 协议桥接层 | `mcp_server/*.py` | Agent 如何跨网络调用 Java ERP |
| 6 | 三层记忆系统 | `agent/memory/*.py` | HOT/WARM/COLD 跨会话记住用户 |
| 7 | Docker 安全沙箱 | `backends/sandbox_*.py` | 7 层防护 + 五态池化 |
| 8 | HITL 审批与子Agent | `hitl_tools.py` `subagents/*` | 写操作如何强制人工确认 |
| 9 | Skills 渐进披露与评测 | `progressive_skills.py` `evals/*` | 技能按需加载 + 如何评测 Agent |

## 第 0 模块：整体架构与启动流程

### 4 个进程
```
浏览器 → ①Frontend(:3000) → ②Backend(:8000) → ③Agent Core → ④MCP(:9000) → ⑤Java ERP(:8081)
```

### 三个启动终端（顺序敏感）
1. MCP：`python -m src.mcp_server.server_main` （先把 ERP 变成 23 工具）
2. 后端：`python -m src.api_view.web_main`
3. 前端：`npm run dev`

### 一条请求旅程
1. 前端 `POST /api/chat/stream`
2. `chat_stream` 鉴权 + 存会话 → 构造 `StreamingResponse`
3. `stream_chat_response` 获取用户独立 Agent session
4. `agent.astream(...)` 三流产出（messages/values/custom）
5. `sse_event()` 转 SSE 协议给前端
6. Agent 内部 Harness 四阶段干活
7. ERP 工具走 MCP 桥接层

### SSE 事件协议
`thinking / phase / todo_update / tool_start / tool_args / tool_result / tool_end / interrupt / review_result / token / done / error`

### 4 个核心设计点
1. 用户级沙箱隔离
2. 中断/恢复（interrupt_on + checkpoint）
3. SSE 双流分离（控制流与内容流）
4. 三层记忆（HOT/WARM/COLD）

## 第 2 模块：Harness 四阶段工作流（核心文件 harness.py / review_policy.py / review_gate.py / harness_config.yaml）

### 核心认知：阶段是 graph state 字段，不是 prompt 口号
HarnessPhaseState 扩展字段：phase / plan / review_result / review_decision。
随 checkpoint 落库、可从 values 流读取，前端不靠正则猜。

### 中间件钩子执行模型
- before_agent：每轮1次，注册正序（做入口审查路由，置 planning）
- after_model：模型每回复1次跑1次（有 tool_calls → executing；同步 todos→plan）
- after_agent：每轮1次，注册【逆序】（评审发生处）
循环：model ↔ tool 多轮，模型给最终答案才退出到 after_agent。

### 阶段写入点
- planning：before_agent 无条件
- executing：after_model 检测 AIMessage.tool_calls（结构信号）
- reviewing：after_agent 读到 needs_revision
- result：其余终态

### Review 三层
1. 入口混合路由 ReviewPolicy.start：
   explicit rubric > 本地规则 rule() > LLM 结构化路由 > 失败/8s超时保守 review。
   ReviewRoute: decision(skip/review/uncertain)+task_type+reason+checks(5选N)。
   extra=forbid，模型只能选预定义检查项，不能改写 BASELINE 固定底线。
2. 注入 rubric（BASELINE+任务模板+checks）→ RubricMiddleware 的 grader 子Agent
   逐条对照 transcript 打分：satisfied / needs_revision / failed。
   needs_revision 靠 @hook_config(can_jump_to=["model"]) 跳回模型，真实回路。
3. 两道防护：
   - ReviewExecutionGate.after_agent（逆序先跑）：扫工具记录，写操作/报错/
     ≥3工具/≥2来源 → 即便入口 skip 也升级 review。
   - SafeRubricMiddleware：写操作用 max_iterations=1 的单轮评审器，
     不通过也不重放，防止重复下单（只读任务才可最多3次打回）。

### DSL：harness_config.yaml
review.mode(auto/always/never)、strategy(hybrid/rules)、router_provider、
router_timeout_seconds、max_iterations、task_types、rubrics(5类评分标准)。
load_harness_config 失败回退 _DEFAULT_CONFIG。

## 待补充（随讲解进度填充）
- 模块 3-9 详细笔记