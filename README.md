# 单智能体基础开发框架

这是一个从 Hookshot 选品智能体提炼出的独立单智能体模板。它保留 LangGraph 节点编排、工具调用、结构化追问、Checkpoint 恢复、取消、统一事件与 SSE 流式能力，不包含选品或商品业务，也不包含多智能体注册、发现和路由。

默认使用内存后端，无需启动 PostgreSQL、Redis 或 Celery。数据库、缓存和任务队列只预留配置与接口，后续接入时无需改动节点和工具的业务边界。

## 目录结构

```text
app/                         FastAPI 路由、请求 DTO、Service 与应用生命周期
agent/
  state.py                   唯一智能体的图状态
  graph.py                   图构建、节点连接和条件路由
  runner.py                  执行、恢复、取消、超时和事件转换
  nodes/                     可独立测试的业务节点
  tools/                     工具实现与唯一工具清单
  prompts/                   系统提示词和版本
  schemas/                   问题、工具结果和运行状态模型
  streaming/                 事件、发布、重放和 SSE 编码
  persistence/               持久化协议与默认内存适配器
infra/
  settings.py                集中配置和外部服务占位项
  model_provider.py          模型 Provider，不在节点内读取环境变量
tests/                       节点、运行器、SSE、API 与基础设施契约测试
main.py                      Uvicorn 入口
```

这里的 `agent/` 就是唯一智能体，不需要复制目录、定义 `agent_id` 或注册 `AgentDefinition`。后续开发通常只修改 `state.py`、`nodes/`、`tools/`、`prompts/` 和 `graph.py`。

## 已具备的基础能力

- 固定单智能体 API：普通响应、SSE 流式响应、恢复和取消
- LangGraph 显式状态、节点、工具与条件边
- `question.required` 结构化追问和相同 Checkpoint 恢复
- 会话级互斥锁、可信主体隔离、运行超时和主动取消
- 最大步骤、工具次数和输出长度保护
- 稳定事件类型、单调 SSE 游标、协议心跳和内存断点重放
- 安全工具返回与统一业务异常，不向用户暴露原始异常
- OpenAI-compatible 模型 Provider，以及离线测试 Provider
- PostgreSQL、Redis、Celery 配置和替换协议占位

## 本地启动

项目目标环境为 Python 3.12；当前测试也兼容 Python 3.11。

```powershell
cd E:\Agent\agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

打开 `http://127.0.0.1:8000/docs` 查看接口。

## API 与 SSE

首次请求会产生结构化追问：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/api/agent/chat/stream `
  -H "Content-Type: application/json" `
  -d '{"message":"帮我梳理一个业务智能体"}'
```

从 `question.required` 读取 `conversation_id` 和 `run_id`，再提交答案：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/api/agent/runs/<run_id>/resume `
  -H "Content-Type: application/json" `
  -d '{"conversation_id":"<conversation_id>","answers":{"goal":"实现订单查询智能体"}}'
```

基础事件包括：

```text
heartbeat
run.started
message.delta
message.completed
tool.started
tool.completed
question.required
run.completed
run.cancelled
run.failed
```

`event_id` 可作为稳定游标。当前 HTTP API 覆盖对话、恢复和取消；`agent/streaming/replay.py` 已提供内部重放接缝，生产接入 Redis Stream 后可按业务鉴权要求增加公开订阅路由。

## 后续业务开发位置

1. 在 `agent/state.py` 增加有界、可序列化的业务状态。
2. 在 `agent/nodes/` 增加职责单一的业务节点；节点不依赖 FastAPI 请求对象。
3. 在 `agent/tools/` 实现有类型约束的工具，并在 `registry.py` 的 `AGENT_TOOLS` 中显式登记。该文件只是唯一智能体的工具清单，不是智能体注册中心。
4. 在 `agent/prompts/` 维护提示词和版本，外部文档、工具结果与用户文本一律作为不可信内容。
5. 在 `agent/graph.py` 连接节点、工具与停止条件。
6. 为每个节点、条件边、工具失败、恢复和 SSE 终止事件增加测试。

真实 LLM 应通过 `infra/model_provider.py` 创建并在应用组装阶段注入节点。不要在节点或工具中散落读取环境变量，也不要把数据库 Session、Redis 客户端、密钥或 HTTP 响应对象写入图状态。

## 数据库、Redis 与 Celery

默认配置为：

```text
CHECKPOINT_BACKEND=memory
LOCK_BACKEND=memory
EVENT_BUS_BACKEND=memory
TASK_BACKEND=disabled
```

`.env.example` 已保留数据库、Redis、Celery 和模型配置项。真实适配器尚未实现；显式切换外部后端时会返回 `BACKEND_NOT_CONFIGURED`，不会尝试连接占位地址。

后续适配器应实现 `agent/persistence/interfaces.py` 中的协议。数据库查询集中在独立 CRUD 层；连接池和客户端在 FastAPI lifespan 中创建、关闭，禁止模块导入时连接网络。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试不访问真实 LLM、数据库、Redis、Celery 或其他第三方服务。
