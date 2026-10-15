# 引入 SQLAlchemy ORM

- 日期：2026-10-15
- 变更类型：架构
- 影响范围：应用数据库模型、PostgreSQL CRUD 持久化、数据库资源生命周期

## 背景

此前 PostgreSQL 表结构和多个数据领域的 SQL 操作集中在单个 CRUD 模块中，使用 psycopg 直接执行 SQL。项目需要采用 ORM，并将数据库模型、连接管理和各领域 CRUD 分开维护。

## 变更内容

- 增加 SQLAlchemy 2.0 依赖，并使用 `postgresql+psycopg` 方言创建 PostgreSQL 引擎和 Session 工厂。
- 增加用户身份、会话、运行、消息和任务结果的 SQLAlchemy 模型；模型与 HTTP DTO、Agent 领域记录分离。
- 将 CRUD 拆分为身份解析、会话、消息、运行、任务结果和运行锁模块；业务数据存储接口保持不变，运行锁释放接口改为异步。
- 将应用启动时的建表逻辑改为 `Base.metadata.create_all`，只创建缺失表；已有表结构仍由迁移脚本管理。
- 更新架构文档和项目级变更日志。

## 涉及文件

- `backend/app/db/`：管理 SQLAlchemy 引擎、Session 工厂和 ORM 表初始化。
- `backend/app/models/`：定义独立的 PostgreSQL 持久化模型和列注释。
- `backend/app/crud/`：按持久化职责实现 ORM 查询、写入和授权校验。
- `backend/app/lifecycle.py`：组装数据库、CRUD 适配器及 Agent Runner。
- `backend/agent/persistence/`、`backend/agent/runner.py`：将运行锁释放改为异步，避免阻塞事件循环。
- `backend/requirements.txt`：加入 SQLAlchemy 依赖。
- `docs/ARCHITECTURE.md`：记录 ORM、数据库资源与 CRUD 的边界。
- `docs/数据库表结构.md`：更新 ORM 模型路径并说明消息唯一约束索引。
- `CHANGELOG.md`：记录未发布的 ORM 架构变化。

## 设计决策

- 使用 SQLAlchemy 2.0 同步 ORM Session，保持现有业务存储协议和同步 CRUD 接口；长持有的 PostgreSQL advisory lock 使用独立 psycopg 连接池，获取和释放操作在线程池中执行，避免占用事件循环或长时间占用 ORM 查询连接。
- 保留 psycopg 作为 SQLAlchemy PostgreSQL 方言驱动以及 LangGraph Checkpointer 所需驱动，不引入第二套 ORM。
- ORM 启动建表只处理缺失表，不负责修改已有表；已有数据结构演进继续通过 `backend/migrations/` 管理。

## 测试与验证

- 命令：在 `backend/` 工作目录执行 `.venv/Scripts/python.exe -m pytest -q`
- 结果：64 项通过；有 1 条 Starlette `BlockingPortal` 弃用警告。
- 命令：在 `backend/` 工作目录执行 `.venv/Scripts/python.exe -m compileall -q agent app agents infra migrations tests`
- 结果：通过。
- 命令：在 `backend/` 工作目录执行 `.venv/Scripts/python.exe -c "from sqlalchemy.dialects.postgresql import dialect; from sqlalchemy.schema import CreateIndex, CreateTable; from app.models import Base; d=dialect(); ddl=[str(CreateTable(table).compile(dialect=d)) for table in Base.metadata.sorted_tables]; ddl += [str(CreateIndex(index).compile(dialect=d)) for table in Base.metadata.sorted_tables for index in table.indexes]; assert all('BIGSERIAL' not in statement for statement in ddl); print('ORM metadata and PostgreSQL DDL compilation passed')"`
- 结果：5 张表和 7 个索引均通过 PostgreSQL 方言编译；主键没有生成自增序列。
- 命令：在项目根目录执行 `git diff --check`
- 结果：通过；Git 提示部分新增或修改文件在后续写入时会进行 LF/CRLF 转换。
- 本次未连接真实 PostgreSQL 实例执行端到端 CRUD 验证。
- 当前工作区没有设置 PostgreSQL 测试数据库 URL，仓库测试也没有 CRUD 集成测试 fixture，因此数据库 CRUD 的实际事务与查询结果仍需在接入测试数据库后验证；本次通过 PostgreSQL 方言 DDL 编译检查验证模型映射。

## 潜在影响

- `Base.metadata.create_all` 只创建缺失的表，不会修复或变更已有数据库表；部署前仍须确保已有数据库已应用匹配的迁移脚本。
- 每个后端进程的 ORM 引擎最多使用 10 个连接，运行锁连接池最多使用 10 个连接；LangGraph Checkpointer 另有自己的连接资源，部署时应将这些连接计入 PostgreSQL 容量。
- Runner 的运行锁释放协议改为异步，以在线程池执行 PostgreSQL 解锁 I/O；内存适配器同步改为异步协议实现。

## 后续事项

- 无。
