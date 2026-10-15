# 重组后端三层结构

- 日期：2026-10-15
- 变更类型：架构
- 影响范围：FastAPI 路由、应用服务、PostgreSQL 持久化适配器及智能体运行器组装

## 背景

项目约定的应用分层为 `router`、`service`、`crud`，并统一放在 `backend/app/` 下。原路由目录名为 `controller`，PostgreSQL 适配器位于 `agent/persistence/`，且 `agent/runner.py` 直接依赖 PostgreSQL 实现。

## 变更内容

- 将 HTTP 路由模块从 `app/controller/` 移至 `app/router/`，并更新应用入口导入。
- 将 PostgreSQL 适配器移至 `app/crud/postgres.py`。
- 将 Runner 构建改为接收存储协议；由应用生命周期创建并注入 PostgreSQL Store，解除 `agent/runner.py` 对 PostgreSQL 实现的直接依赖。
- 保留 `agent/persistence/interfaces.py` 中的运行时协议和内存测试适配器，继续作为 Agent 与具体数据库实现之间的边界。
- 更新后端架构文档和项目变更日志。

## 涉及文件

- `backend/app/router/`：承载原 `controller` 下的 HTTP 路由模块。
- `backend/app/crud/postgres.py`：承载 PostgreSQL 连接池、SQL 操作和 Store 适配器。
- `backend/app/lifecycle.py`：组装 CRUD 实现并注入 Runner。
- `backend/app/main.py`：从新 Router 包注册路由。
- `backend/agent/runner.py`：提供基于持久化协议构建 Runner 的入口，不再导入 PostgreSQL Store。
- `backend/agent/persistence/__init__.py`：更新包职责说明。
- `docs/ARCHITECTURE.md`：记录新的分层目录和依赖方向。
- `CHANGELOG.md`：记录未发布的架构变化。

## 设计决策

- PostgreSQL 实现归属应用的 `crud` 层；Agent Runner 只依赖协议，由 `app/lifecycle.py` 完成具体实现注入。
- 内存适配器和存储协议仍放在 `agent/persistence/`，避免 Agent 运行逻辑导入 FastAPI 应用层。

## 测试与验证

- 命令：在 `backend/` 工作目录执行 `.venv/Scripts/python.exe -m pytest -q`
- 结果：64 项通过；有 1 条 Starlette `BlockingPortal` 弃用警告。
- 命令：在 `backend/` 工作目录执行 `.venv/Scripts/python.exe -m compileall -q agent app agents infra migrations tests`
- 结果：通过。
- 命令：在项目根目录执行 `git diff --check`
- 结果：通过；Git 提示部分文件在后续写入时会进行 LF/CRLF 转换。

## 潜在影响

- 仓库内的旧导入路径已更新；依赖 `app.controller` 或 `agent.persistence.postgres` 的仓库外代码需要改用新路径。
- 本次未单独在真实 PostgreSQL 实例上执行应用启动与数据库端到端验证。

## 后续事项

- 暂无。
