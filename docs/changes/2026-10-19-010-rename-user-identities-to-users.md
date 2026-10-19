# 将 `user_identities` 迁移为 `users` 用户表

- 日期：2026-10-19
- 变更类型：架构
- 影响范围：后端用户模型、用户映射 CRUD、PostgreSQL 用户表及相关文档

## 背景

现有 `user_identities` 仅保存内部用户 ID、可信认证主体和创建时间。用户表需要增加账号、密码哈希及角色字段。

## 变更内容

- 将 ORM 模型改为 `users`，包含 `user_id`、`account`、`password_hash`、`role` 和 `created_at`。
- 将会话、任务结果和文献记录的用户外键更新为 `users.user_id`。
- 用户主体映射改为按 `users.account` 查找；现有可信主体值保留为账号值。
- 新增 `008_user_accounts.sql`，将旧表和字段重命名并增加密码哈希、角色字段；现有用户 ID、账号值、创建时间和外键关系均保留。
- 更新数据库结构说明和未发布变更日志。

## 涉及文件

- `backend/app/models/user.py`：新增用户 ORM 模型。
- `backend/app/models/identity.py`：移除旧模型。
- `backend/app/crud/identity.py`、`backend/app/crud/conversation.py`、`backend/app/crud/run.py`、`backend/app/crud/task_result.py`、`backend/app/crud/literature.py`：改用 `User` 模型及 `account` 字段。
- `backend/migrations/008_user_accounts.sql`：新增现有数据库迁移。
- `backend/app/models/conversation.py`、`backend/app/models/task_result.py`、`backend/app/models/literature.py`：更新用户外键。
- `docs/数据库表结构.md`、`docs/agents/literature-reader/implementation-plan.md`、`CHANGELOG.md`：同步文档。

## 设计决策

- `account` 接收旧 `external_principal` 的值，以保留现有认证主体映射和数据归属。
- `password_hash` 暂时允许为空，因为旧记录没有本地密码凭据；当前变更未增加登录或设置密码流程。
- `role` 限定为 `user` 或 `admin`，新记录默认 `user`。

## 测试与验证

- 命令：`docker compose --env-file backend/.env -f backend/compose.yaml build backend literature-worker`
- 结果：后端和 Worker 镜像构建成功。
- 当前 PostgreSQL：迁移执行成功；`users` 含 `user_id`、`account`、`created_at`、`password_hash`、`role` 五列，原有 1 条用户记录保留，3 个外键约束引用 `users`，`user_identities` 已不存在。
- 后端就绪接口：`GET /health/ready` 返回 HTTP 200，PostgreSQL 和 Redis 检查均为 healthy。
- 未运行自动化测试；本次验证覆盖了镜像构建、实际数据库迁移及服务就绪状态。

## 潜在影响

- 现有用户的 `password_hash` 为空；在实现本地密码登录前，需先为用户设置密码哈希。现有可信主体映射继续可用。

## 后续事项

- 如需账号密码登录，另行实现安全的密码设置、登录和密码重置流程。
