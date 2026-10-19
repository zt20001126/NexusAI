# 保留数据升级旧版智能体数据库结构

- 日期：2026-10-19
- 变更类型：缺陷修复 / 数据库迁移
- 影响范围：已有 PostgreSQL 数据库升级到字符串智能体标识、精简任务结果和会话流续接结构

## 背景

运行中的数据库仍使用 `conversations.agent_id` 和旧版 `task_results` 列。旧迁移 009 会直接删除任务结果，而迁移 010 未识别项目历史上实际使用的静态雪花 ID。

## 变更内容

- 新增一次性迁移 012，在事务和表锁保护下原位转换旧 `task_results` 字段，保留其 JSON 内容和会话/消息关系。
- 迁移前校验智能体 ID、运行/会话/结果/消息关系及状态；不符合条件时回滚。
- 将项目历史静态智能体 ID 映射为当前字符串枚举，并在 010 中补齐该 ID 映射兼容性。
- 更新数据库升级说明和 CHANGELOG，区分会清空数据的旧 009 与数据保留升级路径。
- 已在本地 Compose PostgreSQL 实例应用 012；17 条任务结果保留，全部会话智能体字段转换成功，后端及 Worker 已恢复运行。

## 涉及文件

- `backend/migrations/010_agent_type_strings.sql`：接受项目历史静态 ID。
- `backend/migrations/012_legacy_schema_data_preserving_upgrade.sql`：新增数据保留升级迁移。
- `docs/数据库表结构.md`、`CHANGELOG.md`：更新升级指引与用户可见摘要。

## 设计决策

- 不修改历史 009 的既有清空语义；新增 012 作为旧数据库直接升级到当前模型的兼容迁移。
- 迁移将 `input_data`、`result_data` 原样改名为 `input`、`result`，不读取或重写 JSON 内容。

## 测试与验证

- 命令：通过 `psql` 在事务末尾替换为 `ROLLBACK` 执行迁移脚本。
- 结果：所有验证和 DDL 步骤执行成功，事务回滚，正式迁移前无数据库变更。
- 命令：通过 Docker Compose 对 PostgreSQL 执行迁移 012，并查询会话类型、结果列、记录数、约束和索引。
- 结果：迁移提交成功；7 类会话智能体均已映射；17 条任务结果仍存在；旧 `agent_id` 列已移除；状态约束和幂等索引存在。
- 命令：`GET http://127.0.0.1:8000/health/ready`；检查 `backend`、`agent-worker`、`literature-worker` 日志。
- 结果：就绪接口返回 200，后端启动完成，两个 Worker 均连接 Redis 并进入 ready 状态。
- 备份：迁移前使用 `pg_dump -Fc` 备份到系统临时目录。

## 潜在影响

- 迁移需要短暂锁定会话、运行和任务结果表；升级期间后端和 Worker 应停止。
- 012 仅适用于仍有 `conversations.agent_id`、`agent_runs.agent_id` 和 `task_results.task_result_id` 的旧数据库，不能重复执行。

## 后续事项

- 无。
