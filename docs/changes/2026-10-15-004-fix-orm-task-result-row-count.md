# 修复 ORM 任务结果写入误判

- 日期：2026-10-15
- 变更类型：缺陷修复 / 测试
- 影响范围：PostgreSQL 任务结果保存与状态更新

## 背景

对 ORM 重构后的持久化流程执行真实 PostgreSQL 冒烟验证时，任务结果保存抛出 `ConversationAccessDeniedError`。检查发现当前 SQLAlchemy/psycopg 运行组合在任务结果 upsert 上返回 `rowcount == -1`，旧判断因此把已成功的插入误判为失败。状态更新本身返回有效行数，但也改为用 `RETURNING` 判断命中记录，避免依赖驱动的行数行为。

## 变更内容

- 任务结果 upsert 和状态更新改用 SQLAlchemy `RETURNING` 返回主键，按是否有返回行判断操作结果，不再依赖 `rowcount`。
- 增加回归单元测试，覆盖驱动 `rowcount == -1` 时的成功与未命中行为。
- 增加只允许连接本机 PostgreSQL 的 ORM CRUD 验证脚本；脚本使用随机隔离 schema，验证完成后删除该 schema。

## 涉及文件

- `backend/app/crud/task_result.py`：改用 `RETURNING` 判断任务结果写入和状态更新结果。
- `backend/tests/test_postgres_task_result_crud.py`：新增 DML 返回行回归测试。
- `backend/scripts/verify_postgres_orm.py`：增加真实 PostgreSQL 隔离 schema 冒烟验证。
- `CHANGELOG.md`：记录未发布的缺陷修复。

## 设计决策

- 以数据库返回的主键行确认写入或更新结果，保留现有授权校验和“未命中时拒绝/返回 False”的语义。
- 真实 CRUD 验证只在本机数据库中的临时 schema 执行；脚本遇到非本机数据库会拒绝运行。

## 测试与验证

- 命令：在 `backend/` 工作目录执行 `.venv/Scripts/python.exe -m pytest -q`
- 结果：68 项通过；有 1 条 Starlette `BlockingPortal` 弃用警告。
- 命令：在 `backend/` 工作目录执行 `.venv/Scripts/python.exe -m compileall -q agent app agents infra migrations scripts tests`
- 结果：通过。
- 命令：在 `backend/` 工作目录执行 `.venv/Scripts/python.exe -m pip check`
- 结果：No broken requirements found。
- 命令：在 `backend/` 工作目录执行 `.venv/Scripts/python.exe -m scripts.verify_postgres_orm`
- 结果：通过；在临时 schema 中验证身份、会话、消息、运行、任务结果 CRUD、结果授权过滤及运行锁竞争，结束后删除临时 schema。
- 命令：在 `frontend/` 工作目录执行 `npm run build`
- 结果：TypeScript 检查和 Vite 生产构建通过。
- 命令：在项目根目录执行 `git diff --check`
- 结果：通过；Git 提示 `backend/app/crud/task_result.py` 将在后续写入时转换 LF/CRLF。

## 潜在影响

- 新增 `backend/scripts/verify_postgres_orm.py` 仅用于本机 PostgreSQL 验证，需使用已有 `DATABASE_URL` 配置；不会连接远程主机。

## 后续事项

- 无。
