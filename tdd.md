# 通用智能体基础框架 TDD

## 1. 技术选型确认

- Python：3.12
- Web：FastAPI + Uvicorn
- Agent：LangGraph + LangChain Core
- 数据校验：Pydantic v2
- 流式协议：SSE
- 默认状态存储：进程内存
- 可选持久化：PostgreSQL + LangGraph PostgreSQL Checkpointer
- 可选缓存与协调：Redis
- 可选任务队列：Celery
- 测试：pytest + FastAPI TestClient/HTTPX
- 架构：模块化单体，可插拔基础设施适配器

## 2. 系统架构设计

```text
Client
  ↓ HTTP / SSE
Router
  ↓
Agent Service
  ↓
Agent Registry ──→ Agent Definition
  ↓                    ├── State
Agent Runtime          ├── Prompt
  ├── Graph Executor   ├── Nodes
  ├── Run Coordinator  └── Tools
  ├── Event Publisher
  └── Checkpoint Store
        ↓ 接口选择
  Memory / PostgreSQL / Redis / Celery
```

依赖方向固定为：

```text
app → agent_core ← agents
          ↓
        infra contracts
          ↓
 optional infrastructure implementations
```

业务智能体不得依赖 FastAPI 请求对象、数据库 Session、Redis Client 或 Celery App。需要外部能力时，通过运行上下文或 Integration 接口注入。

## 3. 模块划分

### 3.1 `app`

- 创建 FastAPI 应用。
- 管理应用启动和关闭生命周期。
- 注册智能体查询、对话、恢复和取消路由。
- 将 HTTP 请求转换成 Service DTO。
- SSE 路由只负责响应封装，不执行图业务逻辑。

### 3.2 `agent_core.contracts`

定义稳定公共契约：

- `AgentDefinition`：智能体标识、描述、图工厂和默认配置。
- `AgentRunRequest`：智能体、会话、用户输入和恢复载荷。
- `AgentRunContext`：可信用户、请求、会话和基础设施依赖。
- `AgentEvent`：统一流式事件。
- `ToolResult`：工具统一输出。
- `CheckpointStore`：状态保存与恢复接口。
- `RunLock`：会话锁接口。
- `EventBus`：事件发布和可选重放接口。
- `TaskDispatcher`：长任务提交接口。

### 3.3 `agent_core.graph`

- 提供标准 Agent/Tool 循环构建器。
- 使用命名路由函数判断进入工具、追问或结束。
- 图循环配置最大步数，达到限制后返回稳定错误事件。
- 工具注册表是工具名称的唯一来源。
- 图编译与 Checkpointer 生命周期由应用生命周期管理。

### 3.4 `agent_core.runtime`

- 从注册中心解析智能体。
- 创建或恢复会话运行上下文。
- 获取会话级运行锁。
- 执行 LangGraph 并将底层事件映射为 `AgentEvent`。
- 处理取消、超时、客户端断开和资源清理。
- 统一捕获内部异常，记录详情并输出安全错误。
- 保证逻辑完成事件最多一次。

### 3.5 `agent_core.streaming`

事件类型：

| 类型 | 用途 | 是否持久化 |
| --- | --- | --- |
| `heartbeat` | 保持 SSE 连接 | 否 |
| `message.delta` | 文本增量 | 否 |
| `message.completed` | 完整模型消息 | 是 |
| `tool.started` | 工具开始 | 可选 |
| `tool.completed` | 受控工具摘要 | 可选 |
| `question.required` | 结构化追问及暂停 | 是 |
| `run.completed` | 运行成功结束 | 是 |
| `run.cancelled` | 用户取消 | 是 |
| `run.failed` | 安全失败码和提示 | 是 |

每个事件包含 `event_id`、`event_type`、`conversation_id`、`run_id`、`sequence`、`timestamp` 和受约束的 `data`。首版内存实现生成递增序号；Redis 实现后可将 `event_id` 映射为 Stream 游标。

### 3.6 `agent_core.models`

- `ChatModelProvider` 抽象模型创建和调用配置。
- API Key、Base URL、模型名和超时全部来自集中配置。
- 节点只请求一个已配置的模型实例，不直接读取环境变量。
- 测试使用确定性 Fake Model。

### 3.7 `agent_core.persistence`

默认实现：

- `MemoryCheckpointStore`
- `MemoryConversationStore`
- `MemoryRunLock`
- `MemoryEventBus`
- `DisabledTaskDispatcher`

预留实现：

- `PostgresCheckpointStore`
- `PostgresConversationStore`
- `RedisRunLock`
- `RedisEventBus`
- `CeleryTaskDispatcher`

预留实现可以包含配置模型、接口骨架和清晰的未启用错误，但首版不得在导入时连接外部服务。只有配置启用且应用生命周期启动时，才创建连接池或客户端。

### 3.8 `agents.example_agent`

示例场景采用无外部依赖的“需求助手”：

- 收集目标和期望输出。
- 信息不足时调用结构化追问工具。
- 调用一个本地计算或格式化工具。
- 返回最终摘要。
- 展示状态更新、工具循环、中断和恢复的完整路径。

## 4. 配置设计

配置集中在 `infra/settings.py`，禁止在业务模块散落 `os.getenv()`。

建议占位项：

```dotenv
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000

LLM_PROVIDER=openai_compatible
LLM_MODEL=
LLM_API_KEY=
LLM_BASE_URL=
LLM_TIMEOUT_SECONDS=60

CHECKPOINT_BACKEND=memory
DATABASE_URL=

LOCK_BACKEND=memory
EVENT_BUS_BACKEND=memory
REDIS_URL=

TASK_BACKEND=disabled
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=

AGENT_MAX_STEPS=20
AGENT_RUN_TIMEOUT_SECONDS=180
SSE_HEARTBEAT_SECONDS=15
```

配置校验规则：

- `memory/disabled` 模式不校验对应外部连接地址。
- 启用 PostgreSQL、Redis 或 Celery 时才要求相关 URL 非空。
- 连接字符串和密钥不写入日志或 API 错误。
- 未启用能力被调用时返回稳定的“能力未配置”业务错误。

## 5. 状态设计

通用状态只保存跨节点真正需要的数据：

```text
messages               对话消息，使用 reducer 追加
conversation_id        服务端注入的会话标识
run_id                 当前运行标识
pending_question       等待用户回答的问题
interrupt_status       running/waiting/resumed/cancelled
tool_call_count        工具调用计数
last_error_code        可持久化的安全错误码
metadata               有界、可序列化的扩展元数据
```

业务智能体通过继承或组合增加自己的状态字段。用户身份、数据库 Session、Redis Client、密钥和不可序列化对象不得写入图状态。

## 6. API 设计

### 6.1 查询智能体

```http
GET /api/agents
```

返回已注册智能体的 `agent_id`、名称、描述和能力摘要。

### 6.2 普通对话

```http
POST /api/agents/{agent_id}/chat
```

请求包含可选 `conversation_id`、用户消息和有界业务输入；返回完整运行结果。

### 6.3 流式对话

```http
POST /api/agents/{agent_id}/chat/stream
```

返回 `text/event-stream`。协议使用统一 `AgentEvent`，不透传 LangGraph 或供应商原始事件。

### 6.4 恢复运行

```http
POST /api/agents/{agent_id}/runs/{run_id}/resume
```

提交结构化问题答案。服务端校验当前会话、运行状态和问题标识后恢复图。

### 6.5 取消运行

```http
POST /api/agents/{agent_id}/runs/{run_id}/cancel
```

设置取消信号；内存模式使用本地协调器，Redis 模式使用带 TTL 的取消键。

## 7. 数据库设计预留

首版不创建或要求数据库，但预留以下领域模型及迁移边界：

- `agent_conversations`：会话所有者、智能体标识、状态和时间。
- `agent_messages`：角色、受控内容、顺序和消息类型。
- `agent_runs`：运行状态、错误码、开始/结束时间和幂等键。
- LangGraph Checkpoint 表：由官方 PostgreSQL Checkpointer 管理。

未来实现要求：

- API Schema 与数据库 Model 分离。
- 所有 SQL 仅存在于持久化或 CRUD 实现。
- 多次写入由 Service 定义事务边界。
- 所有会话和运行查询按可信用户或租户过滤。
- PostgreSQL 保存业务事实；Redis 不作为唯一持久化来源。
- 不在模块导入时自动建表或执行迁移。

## 8. 缓存与任务设计预留

### Redis

- 会话锁：`agent:{env}:lock:{conversation_id}`，设置 TTL 并支持续期。
- 取消标记：`agent:{env}:cancel:{run_id}`，设置有限 TTL。
- 事件流：`agent:{env}:events:{conversation_id}`，限制长度和保留时间。
- 所有订阅、恢复和取消仍需服务端鉴权，不能凭 Redis Key 授权。

### Celery

- 只用于长耗时、轮询、批处理或 CPU 密集任务。
- 任务参数只传可序列化标识和值。
- 任务具备软硬超时、幂等键和安全失败码。
- 默认 `TASK_BACKEND=disabled`，首版同步示例不依赖 Worker。

## 9. 核心流程

### 9.1 普通执行

```text
请求校验
→ 解析 AgentDefinition
→ 获取会话锁
→ 创建运行上下文
→ 加载 Checkpoint
→ 执行 Agent 节点
→ 若有工具调用，校验并执行工具
→ 返回 Agent 节点继续推理
→ 输出最终消息
→ 保存状态
→ 发布 run.completed
→ 清理资源并释放锁
```

### 9.2 追问恢复

```text
Agent 判断信息不足
→ 调用结构化追问工具
→ 校验问题载荷
→ 保存 waiting 状态
→ 发布 question.required
→ 当前运行暂停
→ 用户提交答案
→ 校验归属、run_id 和问题 ID
→ 恢复 Checkpoint
→ 将答案写入受控消息/状态
→ 继续执行图
```

### 9.3 基础设施选择

```text
读取集中配置
→ backend=memory/disabled：创建本地实现
→ backend=postgres/redis/celery：校验对应配置
→ 在应用 lifespan 创建客户端
→ 健康检查失败时按配置选择启动失败或明确降级
→ lifespan 结束时关闭连接
```

## 10. 异常与安全设计

- 业务可预期异常使用稳定错误码，例如 `AGENT_NOT_FOUND`、`RUN_BUSY`、`RUN_NOT_RESUMABLE`。
- 未知异常记录完整内部日志，对外统一为 `AGENT_RUN_FAILED`。
- 工具、SSE、状态和持久化消息都不得包含 `str(exc)`。
- 模型输出的工具名必须存在于当前智能体注册表。
- 工具参数必须通过 Pydantic 校验，拒绝未知或超限字段。
- 外部内容与系统提示词分隔，并限制注入长度。

## 11. 测试设计

- 配置测试：默认无外部服务可启动；启用后缺少 URL 会失败。
- Registry 测试：注册、重复注册、不存在智能体。
- Graph 测试：每条条件路由、工具循环和最大步数终止。
- Node 测试：使用 Fake Model 验证状态更新和错误分支。
- Tool 测试：参数边界、未知工具、安全错误、超时和幂等预留。
- Resume 测试：问题暂停、合法恢复、重复恢复和越权恢复。
- SSE 测试：心跳、顺序、终止事件唯一性和安全错误。
- Runtime 测试：同会话并发、取消、客户端断开和清理。
- 基础设施契约测试：Memory 实现与预留接口行为一致。

## 12. 实施边界

本轮后续代码抽取只实现内存模式的完整闭环，并为 PostgreSQL、Redis、Celery建立配置模型、抽象接口和工厂分支。除非用户进一步授权，不安装、启动或连接这些外部服务，也不写入真实连接信息。
