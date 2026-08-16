# 通用智能体基础框架

这是一个从 Hookshot 选品智能体提炼出的独立基础框架。它保留 LangGraph 编排、工具调用、结构化追问、Checkpoint 恢复、统一事件和 SSE 能力，不包含选品、商品或第三方市场数据业务。

默认使用内存后端，无需安装或启动 PostgreSQL、Redis、Celery。相关配置和公开接口已经预留，后续接入真实实现时不需要改变业务智能体的节点与工具代码。

## 当前能力

- FastAPI 普通对话和 SSE 流式接口
- 线程安全的智能体注册中心
- 标准 `Agent → Tool → Agent` LangGraph 循环
- 结构化追问、暂停及同一 Checkpoint 恢复
- 会话级内存锁、取消标记和有序事件编号
- 统一安全错误与工具返回契约
- OpenAI-compatible 模型 Provider（按需创建）
- PostgreSQL、Redis、Celery 配置和适配协议预留
- 无网络依赖的示例智能体及自动化测试

## 目录

```text
app/                    FastAPI 路由、DTO 和应用工厂
agent_core/
  contracts/            智能体、事件、工具和基础设施公开契约
  graph/                通用 LangGraph 构建器
  models/               LLM Provider
  persistence/          内存状态、锁和事件序号
  runtime/              执行、恢复、取消和事件转换
agents/example_agent/   可复制参考的示例业务智能体
infra/                  集中配置
tests/                  公共接口和契约测试
```

## 本地启动

当前开发机器可以使用 Python 3.11 验证，生产目标建议 Python 3.12。

```powershell
cd E:\Agent\agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

打开 `http://127.0.0.1:8000/docs` 查看接口。

示例智能体是确定性本地实现，因此即使 `LLM_API_KEY` 为空也可以演示完整流程。真实业务智能体调用 `OpenAICompatibleProvider.create_chat_model()` 时，才要求配置模型名和密钥。

## 调用示例

第一次请求会返回结构化问题：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/api/agents/example/chat/stream `
  -H "Content-Type: application/json" `
  -d '{"message":"帮我梳理一个业务智能体"}'
```

从 `question.required` 事件读取 `conversation_id` 和 `run_id`，然后恢复：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/api/agents/example/runs/<run_id>/resume `
  -H "Content-Type: application/json" `
  -d '{"conversation_id":"<conversation_id>","answers":{"goal":"实现订单查询智能体"}}'
```

## 开发新的业务智能体

1. 在 `agents/<business_agent>/` 创建 `state.py`、`tools.py`、`graph.py` 和 `definition.py`。
2. 在 `state.py` 中只保存可序列化业务状态，不放数据库会话、Redis 客户端、密钥或用户身份对象。
3. 使用 Pydantic 或 LangChain `@tool` 定义有界工具输入。工具失败时记录真实异常，但只返回稳定错误码和安全提示。
4. 使用 `agent_core.graph.react.build_react_graph` 构建标准工具循环；特殊业务可以自行构建 LangGraph，但仍返回编译图。
5. 创建 `AgentDefinition`，通过 `AgentRuntime.register()` 注册。
6. 为节点路由、工具边界、中断恢复、最大循环和 SSE 终止事件增加测试。

最小注册代码：

```python
from agent_core.contracts.agent import AgentDefinition

definition = AgentDefinition(
    agent_id="order_query",
    name="订单查询智能体",
    description="帮助用户查询和解释订单状态",
    graph_factory=create_order_query_graph,
)
runtime.register(definition)
```

如果业务需要真实 LLM，可在应用组装阶段创建 Provider，并通过闭包或依赖容器注入 Agent 节点。不要在节点内直接读取环境变量。

## 基础设施后续接入

当前仅完整实现 `memory/disabled`：

- `CHECKPOINT_BACKEND=memory`
- `LOCK_BACKEND=memory`
- `EVENT_BUS_BACKEND=memory`
- `TASK_BACKEND=disabled`

PostgreSQL、Redis 或 Celery 的配置值可以写入 `.env`，但真实适配器尚未实现。显式切换到外部后端时，框架会返回 `BACKEND_NOT_CONFIGURED`，不会尝试连接占位地址。

后续实现应分别落在 `agent_core/persistence/` 或独立集成模块，并遵循 `agent_core.contracts.infrastructure` 中的协议。连接池必须在 FastAPI lifespan 中创建和关闭，不能在模块导入时连接网络。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试使用内存 Checkpointer 和确定性示例节点，不会访问真实 LLM、数据库、Redis 或 Celery。

## 安全边界

- API、工具和模型结构化输出必须校验长度与类型。
- 不把 `str(exc)`、堆栈、SQL、连接地址、密钥或内部路径返回用户或模型。
- 工具名称只来自当前智能体注册的工具表。
- Redis Key、Stream ID、Run ID 不能代替用户身份和资源授权。
- 生产接入用户系统后，应从服务端鉴权依赖注入身份，并在持久化查询中按用户或租户过滤。

