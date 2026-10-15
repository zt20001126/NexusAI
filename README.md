# NexusAI 多智能体基础框架

这是一个基于 FastAPI、LangGraph 和 React 的模块化智能体项目。共享运行时提供节点编排、结构化追问、Checkpoint 恢复、取消、统一事件和 SSE；每个业务智能体放在独立目录并通过 `agent_id` 注册。当前包含通用智能体和面向淘宝商品主图、详情页图片的淘宝图片智能体。

![NexusAI 项目标志](frontend/public/brand/nexusai-logo.png)

应用固定使用 PostgreSQL 保存 LangGraph Checkpoint、会话、消息、运行状态和统一智能体任务结果；淘宝图片智能体通过私有阿里云 OSS 保存生成图片和参考图，数据库只保存雪花 ID 与对象元数据。内存适配器由测试显式注入，不是应用运行配置选项。

仓库采用 Monorepo：Python/FastAPI 后端位于 `backend/`，React + TypeScript + Vite 前端位于 `frontend/`。项目文档集中放在 `docs/`；辅助脚本按需放在 `scripts/`。

## 文档导航

从 [`docs/README.md`](docs/README.md) 查看文档目录。首次了解项目，建议先读本文的启动说明，再读[后端架构约定](docs/ARCHITECTURE.md)；接口说明见[API 文档](docs/API接口文档.md)，数据库字段说明见[数据库结构文档](docs/数据库表结构.md)。

## 目录结构

```text
backend/
  app/                       FastAPI 路由、请求 DTO、Service 与应用生命周期
  agent/                     共享运行时及现有默认智能体图
    state.py                 默认智能体图状态
    graph.py                 默认图构建、节点连接和条件路由
    runner.py                执行、恢复、取消、超时和事件转换
    nodes/                   可独立测试的业务节点
    tools/                   工具实现与唯一工具清单
    prompts/                 系统提示词和版本
    schemas/                 问题、工具结果和运行状态模型
    streaming/               稳定事件、发布和 SSE 编码
    persistence/             持久化协议及 PostgreSQL、内存适配器
  agents/                    独立业务智能体与注册中心
    registry.py              agent_id 到定义和应用服务的显式映射
    image_generation/        淘宝电商图片图、节点、TokenHub 工具与 Provider
    listing_agent/           淘宝 Listing 图片识别、必要信息追问和多版本生成
  infra/                     集中配置与外部服务适配
  tests/                     节点、运行器、SSE、API 与契约测试
  main.py                    Uvicorn 入口
  pyproject.toml             Python 项目与 pytest 配置
  requirements.txt           Python 依赖
  .env.example               后端环境变量模板
frontend/                    React + TypeScript + Vite 前端
  src/
    shared/api/              与具体业务无关的 HTTP、SSE 传输能力
    features/chat/           聊天功能及其页面入口
      api/                    聊天 API 与后端数据类型
      components/             聊天功能专属 UI
      hooks/                  会话状态与交互编排
      model/                  聊天视图模型与数据转换
    App.tsx                   前端应用入口
    main.tsx                  React 挂载与全局样式入口
docs/                        项目级文档（按需添加）
scripts/                     项目级辅助脚本（按需添加）
```

前端按功能组织代码。新页面或业务能力优先放入对应的 `features/<feature>/`；只有多个功能共同使用的基础能力才放在 `shared/`。功能内部的 API、UI、状态编排和视图模型分别归入 `api/`、`components/`、`hooks/` 和 `model/`，避免页面直接承载请求与复杂状态逻辑。

`backend/agent/` 承载共享运行时和现有默认智能体的业务图。新增业务智能体应放入 `backend/agents/<business_name>/`，并在 `backend/agents/registry.py` 显式注册；不同图复用 Runner、SSE、追问协议、Checkpointer 和持久化适配器。

## 已具备的基础能力

- 淘宝 Listing 生成智能体：识别商品外观与包装文字，核实必要信息后生成 3 个可选版本，并保存完整 JSON 结果
- 多智能体发现与按 `agent_id` 调用：普通响应、SSE 流式响应、恢复和取消
- LangGraph 显式状态、节点、工具与条件边
- `question.required` 结构化追问和相同 Checkpoint 恢复
- 会话级互斥锁、可信主体隔离、运行超时和主动取消
- 最大步骤、工具次数和输出长度保护
- 稳定事件类型、单调 SSE 游标和协议心跳
- 安全工具返回与统一业务异常，不向用户暴露原始异常
- DeepSeek 对话模型与工具调用；测试通过可替换 Provider 离线运行
- PostgreSQL Checkpoint、会话元数据、消息和运行状态持久化
- 使用共享 `task_results` 表保存智能体输出，并按用户授权读取图片结果
- 淘宝图片智能体支持 PNG/JPEG 参考图、TokenHub 图片生成、参数选项追问和历史结果展示

## 快速开始

### 本机运行后端

项目运行环境固定为 Python 3.12.13。

```powershell
conda create --name nexusai python=3.12.13
conda activate nexusai
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
# 填写模型密钥和 PostgreSQL 配置；本机运行后端时 DATABASE_URL 使用 localhost:5433
docker compose --env-file backend/.env -f backend/compose.yaml up -d postgres
cd backend
python -m pip install -r requirements.txt
$env:LANGGRAPH_STRICT_MSGPACK = "true"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

首次启动前，请在 `backend/.env` 中将 `DEEPSEEK_API_KEY` 的占位值替换为你的 DeepSeek API Key；占位值无法通过启动配置校验。要使用淘宝图片智能体，还需配置 TokenHub API Key 和阿里云 OSS 参数；OSS Bucket 应设为私有。

打开 `http://127.0.0.1:8000/docs` 查看接口。

### 启动前端

另开一个终端启动前端开发服务器：

```powershell
cd frontend
npm install
npm run dev
```

Vite 会将 `/api` 请求代理到 `http://127.0.0.1:8000`。

### 使用 Docker 启动后端

先将 `backend/.env.example` 复制为 `backend/.env`，并填写 DeepSeek API Key 和 PostgreSQL 密码。然后在项目根目录执行：

```powershell
docker compose --env-file backend/.env -f backend/compose.yaml up --build
```

停止服务：

```powershell
docker compose --env-file backend/.env -f backend/compose.yaml down
```

Compose 配置位于 `backend/compose.yaml`，包含以下服务：

- `backend`：FastAPI 服务，使用 Python 3.12.13，并以非 root 用户运行。
- `postgres`：PostgreSQL 17；数据保存在 `nexusai_postgres_data` 卷中。Compose 网络内的连接地址为 `postgres:5432`。
- `redis`：Redis 7，启用 AOF；数据保存在 `nexusai_redis_data` 卷中，宿主机连接地址为 `localhost:6379`。当前应用尚未使用 Redis。

`.env` 仅作为配置来源，不会打包进后端镜像。

## API 与 SSE

当前前端支持从智能体选择器切换到淘宝图片智能体。新接口使用 `agent_id` 路径：

```powershell
curl.exe http://127.0.0.1:8000/api/agents
curl.exe -N -X POST http://127.0.0.1:8000/api/agents/taobao_image/chat/stream `
  -H "Content-Type: application/json" `
  -d '{"message":"帮我生成一张淘宝商品主图"}'
```

首次请求会产生结构化追问；从 `question.required` 读取 `conversation_id` 和 `run_id`，再使用同一个智能体路由提交答案：

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/api/agents/taobao_image/runs/<run_id>/resume `
  -H "Content-Type: application/json" `
  -d '{"conversation_id":"<conversation_id>","answers":{"image_size":"1:1 方图（1024×1024）"}}'
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
task_result.updated
run.completed
run.cancelled
run.failed
```

SSE 事件通过 `event_id` 标识当前进程内的递增游标。当前 HTTP API 覆盖对话、恢复和取消，不保存事件历史，也不支持断线续传；如后续需要重放，应再按实际持久化和鉴权要求设计事件存储与订阅接口。

完整参数、事件、上传和结果读取说明见[API 接口文档](docs/API接口文档.md)。原有 `/api/agent/*` 默认智能体路由保留兼容。

## 后续业务开发位置

1. 新业务智能体放入 `backend/agents/<business_name>/`，按业务维护状态、节点、提示词、工具和图。
2. 在 `backend/agents/registry.py` 登记稳定的 `agent_id` 与定义。
3. 在 `app/lifecycle.py` 组装业务图、Provider、Runner 和应用 Service。
4. 共享运行时扩展放入 `backend/agent/runner.py`、`streaming/`、`schemas/` 或 `persistence/`，避免在业务智能体之间复制公共代码。
5. 为节点、工具失败、追问恢复、持久化和授权接口增加离线测试。

默认图使用 `backend/infra/model_provider.py` 中的 Provider 创建 DeepSeek 模型，并绑定 `backend/agent/tools/registry.py` 登记的工具。图片图通过注入的 TokenHub Provider 调用生图服务。模型配置集中在 `AppSettings`；不要在节点或工具中直接读取环境变量，也不要把数据库连接、密钥或 HTTP 响应对象写入图状态。

### Listing 生成智能体

在选择 Listing 生成智能体后上传商品图片，并可在消息中附加任意已知商品信息。系统会一次性询问当前必要信息；全部问题回答后生成 3 个版本，详情描述为纯文本。视觉模型通过 TENCENT_TOKENHUB_VISION_MODEL 配置，默认为 hy-vision-2.0-instruct，完整 JSON 可在对话结果卡片中查看和切换版本。

## 数据库配置

默认运行配置为：

```text
DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5433/nexusai
```

`DATABASE_URL` 是应用唯一的数据库连接配置，不需要额外设置 `CHECKPOINT_BACKEND`。`backend/.env.example` 中的 `POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD` 仅用于 Compose 初始化数据库容器。应用启动时会自动创建运行元数据表和 LangGraph Checkpoint 表。宿主机运行后端时数据库地址为 `localhost:5433`；Compose 中后端通过服务名 `postgres:5432` 连接数据库。PostgreSQL 保存会话图状态、消息、运行记录和统一 `task_results`；图片字节存放在阿里云 OSS，运行锁由数据库 advisory lock 协调。业务表使用雪花 `BIGINT` ID，API 以十进制字符串传输。

淘宝图片智能体使用 `TENCENT_TOKENHUB_API_KEY`、`TENCENT_TOKENHUB_BASE_URL`、`TENCENT_HY_IMAGE_MODEL` 和 `TENCENT_HY_IMAGE_ENDPOINT`。图片上传与生成还需要 `ALIYUN_OSS_ACCESS_KEY_ID`、`ALIYUN_OSS_ACCESS_KEY_SECRET`、`ALIYUN_OSS_ENDPOINT` 和 `ALIYUN_OSS_BUCKET`。未配置这些凭据不会阻止其他智能体运行；图片上传或保存会返回受控配置错误。Bucket 应为私有，并为每个并发后端进程设置唯一 `SNOWFLAKE_WORKER_ID`。旧数据库升级步骤见[数据库结构说明](docs/数据库表结构.md)。

连接池和 Checkpointer 在 FastAPI lifespan 中创建并关闭，不会在模块导入时连接数据库。应用启动必须能通过 `DATABASE_URL` 访问 PostgreSQL；测试可显式注入内存适配器。

## 测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

测试不访问真实 LLM、数据库或其他第三方服务。
