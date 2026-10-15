# 修复雪花 ID 迁移中的文本默认值冲突

- 日期：2026-10-14
- 变更类型：缺陷修复 / 数据模型迁移
- 影响范围：旧版 PostgreSQL 数据库升级和后端启动

## 背景

旧版迁移 002 为 `conversations.agent_id` 和 `agent_runs.agent_id` 设置了文本默认值 `default`。迁移 003 将两列改为 `BIGINT` 时没有先移除默认值，PostgreSQL 因无法将该默认值自动转换为 `BIGINT` 而中止事务，旧数据库仍缺少当前后端启动所需的 `task_results.input_data` 列。

## 变更内容

- 在迁移 003 修改 `agent_id` 列类型前移除旧文本默认值；记录值由迁移中的映射逻辑转换为对应智能体的雪花 ID。
- 在本地 Compose 数据库完成 003 迁移。按用户确认将 15 条等待中的运行标记为取消，并将 1 张旧结果图转存至 OSS。

## 涉及文件

- `backend/migrations/003_snowflake_ids_oss_task_results.sql`：修改 ID 类型前移除旧默认值。
- `CHANGELOG.md`：记录未发布的迁移修复。

## 设计决策

- 只删除 `agent_id` 的列默认值；迁移按每行现有智能体代码映射到雪花 ID，不依赖文本默认值。
- 执行数据库迁移前创建并检查了自定义格式备份。

## 测试与验证

- 命令：通过 Compose 中的 `pg_dump -Fc` 创建备份，并用 `pg_restore --list` 读取目录。
- 结果：备份非空且可读取，目录包含 59 项。
- 命令：`python -m migrations.migrate_media_to_oss`
- 结果：转存 1 条 `task_results` 结果图，附件转存 0 条。
- 命令：通过 Compose 中的 `psql -v ON_ERROR_STOP=1` 执行 `003_snowflake_ids_oss_task_results.sql`。
- 结果：首次执行因旧默认值失败且事务回滚；修复迁移脚本后再次执行并提交成功。
- 验证：查询确认业务 ID 列为 `BIGINT`、`input_data` 和 `result_data` 为非空 `JSONB`、8 个外键存在、附件表已删除，结果图关联 OSS 元数据；后端重新构建启动，`GET /openapi.json` 返回 HTTP 200。
- 自动化测试未运行；本次验证目标是数据库迁移和服务启动。

## 潜在影响

- 按用户确认，原有 15 条 `waiting` 运行记录已改为 `cancelled`，这些运行不能继续执行。

## 后续事项

- 无。
