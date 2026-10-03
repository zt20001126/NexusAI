# Backend 架构约定

## 当前依赖方向

```text
HTTP -> app.controller -> app.service -> agent.runner -> agent.persistence
                      \-> app.schemas
app.main -> app.lifecycle -> Agent runtime、Provider 与持久化适配器
```

- `app/controller/` 是 HTTP 接口层，只做参数接收、依赖解析、调用 Service 和 JSON/SSE 协议转换。
- `app/service/` 编排应用用例；它不依赖 FastAPI 请求对象，也不访问 SQL。
- `app/repositories/` 当前有意不创建：仓库没有脱离 Agent runtime 的业务 CRUD 资源。新增普通业务数据时，再按资源添加 Repository，并由对应 Service 调用。
- `agent/persistence/` 是 Agent 基础能力的一部分，保存 Checkpoint 周边的会话、消息和运行状态，并提供进程内事件序号。当前不持久化 SSE 事件，也不提供断线重放。它不是通用业务 Repository，不依赖 `app`，由 Agent runtime 按协议使用。
- `infra/model_provider.py` 创建对话模型；`infra/settings.py` 管理模型、数据库和 Agent 运行设置。AI Provider、Agent、Tools 和 Persistence 不属于 HTTP 三层。

## 公共边界

- `app/schemas/` 保存 HTTP 请求/响应 Pydantic Schema。`agent/schemas/` 保存 Agent 内部状态、事件及运行数据；两者不混用。
- 当前没有 SQLAlchemy ORM Model。Agent 持久化适配器管理自己的 SQL 表；未来若引入普通业务 ORM，Model 应放在对应业务模块中，和 API Schema 分开。
- `infra/settings.py` 是统一配置入口，使用 Pydantic Settings 读取环境变量；Controller 和 Service 通过依赖或构造注入消费配置。
- `agent/errors.py` 定义 Agent 领域异常；`app/exceptions/handlers.py` 将其映射成 HTTP 响应，避免 Agent 依赖 FastAPI。
- `app/dependencies/` 保存 HTTP 依赖，例如可信主体解析。应用资源组装放在 `app/lifecycle.py`，HTTP 应用入口放在 `app/main.py`。

## 扩展约定

后续知识库或普通业务 CRUD 可在 `app/modules/<业务>/` 下增加 `controller/`、`service/`、`repository/`、`models/` 和 `schemas/`；只在确有持久化实体时添加 Model 与 Repository。MCP 接入属于工具/基础能力时放在 Agent Tools 或独立集成模块，由 Service 或 Agent 按用例协调。RAG 的文档处理、切分、Embedding、检索和生成作为独立 AI 模块，不放进通用 Controller、Repository 或 Agent Service。

新增依赖必须朝调用方向流动：Controller 可调用 Service，Service 可调用 Repository 或独立基础能力；Repository 不反向依赖 Service/Controller。Agent 与基础能力模块不导入 `app`。
