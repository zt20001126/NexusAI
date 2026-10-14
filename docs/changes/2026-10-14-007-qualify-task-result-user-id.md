# 修复任务结果查询中的 user_id 歧义

- 日期：2026-10-14
- 变更类型：缺陷修复
- 影响范围：会话历史中的任务结果查询

## 背景

读取会话任务结果时，SQL 联接了 `task_results` 和 `user_identities`，两张表都包含 `user_id`。查询未限定所选 `user_id` 的表名，PostgreSQL 因列名歧义而拒绝执行。

## 变更内容

- 为任务结果查询中的字段统一添加 `task_results` 表名前缀，明确列的来源。

## 涉及文件

- `backend/agent/persistence/postgres.py`：限定联表查询的列名。
- `CHANGELOG.md`：记录未发布修复。

## 设计决策

- 保留查询字段和结果映射，仅明确字段所属表；不改动用户身份数据。

## 测试与验证

- 命令：`docker compose up -d --build backend`
- 结果：后端容器重新构建并启动。
- 验证：`GET /openapi.json` 返回 HTTP 200，日志显示应用启动完成。
- 自动化测试及会话历史接口请求未运行。

## 潜在影响

- 暂无已知影响。

## 后续事项

- 无。
