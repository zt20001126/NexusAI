# 单智能体基础开发框架

这是一个从 Hookshot 选品智能体提炼出的独立单智能体模板。它保留 LangGraph 节点编排、工具调用、结构化追问、Checkpoint 恢复、取消、统一事件与 SSE 流式能力，不包含选品或商品业务，也不包含多智能体注册、发现和路由。

应用通过配置使用 PostgreSQL 保存 LangGraph Checkpoint、会话所有权、运行状态和 SSE 事件；内存后端仅供离线测试或显式选择时使用。

仓库采用 Monorepo：Python/FastAPI 后端位于 `backend/`，React + TypeScript + Vite 前端位于 `frontend/`。项目级文档和脚本放在根目录的 `docs/`、`scripts/` 等目录。

## 目录结构

```text
backend/
  app/                       FastAPI 路由、请求 DTO、Service 与应用生命周期
  agent/                     单智能体运行时
    state.py                 唯一智能体的图状态
    graph.py                 图构建、节点连接和条件路由
    runner.py                执行、恢复、取消、超时和事件转换
    nodes/                   可独立测试的业务节点
    tools/                   工具实现与唯一工具清单
    prompts/                 系统提示词和版本
    schemas/                 问题、工具结果和运行状态模型
    streaming/               事件、发布、重放和 SSE 编码
    persistence/             持久化协议及 PostgreSQL、内存适配器
  infra/                     集中配置与外部服务适配
  tests/                     节点、运行器、SSE、API 与契约测试
  main.py                    Uvicorn 入口
  pyproject.toml             Python 项目与 pytest 配置
  requirements*.txt          Python 依赖
  .env.example               后端环境变量模板
frontend/                    React + TypeScript + Vite 前端
docs/                        项目级文档（按需添加）
scripts/                     项目级辅助脚本（按需添加）
```

这里的 `backend/agent/` 就是唯一智能体，不需要复制目录、定义 `agent_id` 或注册 `AgentDefinition`。后续开发通常只修改该目录中的 `state.py`、`nodes/`、`tools/`、`prompts/` 和 `graph.py`。

## 已具备的基础能力

- 固定单智能体 API：普通响应、SSE 流式响应、恢复和取消
- LangGraph 显式状态、节点、工具与条件边
- `question.required` 结构化追问和相同 Checkpoint 恢复
- 会话级互斥锁、可信主体隔离、运行超时和主动取消
- 最大步骤、工具次数和输出长度保护
- 稳定事件类型、单调 SSE 游标、协议心跳和内存断点重放
- 安全工具返回与统一业务异常，不向用户暴露原始异常
- DeepSeek 对话模型与工具调用；测试通过可替换 Provider 离线运行
- PostgreSQL Checkpoint、会话元数据、运行状态和有界 SSE 事件历史持久化

## 本地启动

项目运行环境固定为 Python 3.12.13。

```powershell
conda create --name nexusai python=3.12.13
conda activate nexusai
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
# 填写模型密钥和 PostgreSQL 配置；本地 DATABASE_URL 密码需与 POSTGRES_PASSWORD 一致
docker compose --env-file backend/.env -f backend/compose.yaml up -d postgres
cd backend
python -m pip install -r requirements-dev.txt
$env:LANGGRAPH_STRICT_MSGPACK = "true"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

首次启动前，请在 `backend/.env` 中将 `DEEPSEEK_API_KEY` 的占位值替换为你的 DeepSeek API Key；占位值无法通过启动配置校验。

打开 `http://127.0.0.1:8000/docs` 查看接口。

### 使用 Docker 启动后端

先将 `backend/.env.example` 复制为 `backend/.env`，并填写 DeepSeek API Key 和 PostgreSQL 密码。然后在项目根目录执行：

```powershell
docker compose --env-file backend/.env -f backend/compose.yaml up --build
```

停止服务：

```powershell
docker compose --env-file backend/.env -f backend/compose.yaml down
```

Compose 配置位于 `backend/compose.yaml`。项目名为 `nexusai`，服务名为 `backend` 和 `postgres`；它会启动后端和 PostgreSQL 17，数据库数据保存在 Docker 命名卷 `nexusai_postgres_data` 中。后端容器使用 Python 3.12.13，并以非 root 用户运行；`.env` 仅作为配置来源，不会打包进镜像。

在另一个终端启动前端：

```powershell
cd frontend
npm install
npm run dev
```

Vite 开发服务器将 `/api` 请求代理到 `http://127.0.0.1:8000`。

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

`event_id` 可作为稳定游标。当前 HTTP API 覆盖对话、恢复和取消；`backend/agent/streaming/replay.py` 已提供内部重放接缝，生产接入 Redis Stream 后可按业务鉴权要求增加公开订阅路由。

## 后续业务开发位置

1. 在 `backend/agent/state.py` 增加有界、可序列化的业务状态。
2. 在 `backend/agent/nodes/` 增加职责单一的业务节点；节点不依赖 FastAPI 请求对象。
3. 在 `backend/agent/tools/` 实现有类型约束的工具，并在 `registry.py` 的 `AGENT_TOOLS` 中显式登记。该文件只是唯一智能体的工具清单，不是智能体注册中心。
4. 在 `backend/agent/prompts/` 维护提示词和版本，外部文档、工具结果与用户文本一律作为不可信内容。
5. 在 `backend/agent/graph.py` 连接节点、工具与停止条件。
6. 为每个节点、条件边、工具失败、恢复和 SSE 终止事件增加测试。

默认图使用 `backend/infra/model_provider.py` 中的 Provider 创建 DeepSeek 模型，并绑定 `backend/agent/tools/registry.py` 登记的工具。模型配置集中在 `AppSettings`；不要在节点或工具中直接读取环境变量，也不要把数据库 Session、密钥或 HTTP 响应对象写入图状态。

## 数据库配置

默认运行配置为：

```text
CHECKPOINT_BACKEND=postgres
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/nexusai
```

`backend/.env.example` 还包含 DeepSeek、腾讯混元生图极速版、火山引擎 Seedream 和智能体运行限制配置。应用启动时会自动创建运行元数据表和 LangGraph Checkpoint 表。宿主机运行后端时数据库地址为 `localhost:5432`；Compose 中后端通过服务名 `postgres:5432` 连接数据库。PostgreSQL 保存会话图状态、运行记录和事件重放历史；运行锁由数据库 advisory lock 协调。

连接池和 Checkpointer 在 FastAPI lifespan 中创建并关闭，不会在模块导入时连接数据库。内存适配器仍可用于测试，应用配置 `CHECKPOINT_BACKEND=memory` 时不需要 PostgreSQL。

## 测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

测试不访问真实 LLM、数据库或其他第三方服务。
