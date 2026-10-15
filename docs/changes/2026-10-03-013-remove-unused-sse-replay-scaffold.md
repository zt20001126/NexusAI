# 删除未接入的 SSE 重放骨架

- 日期：2026-10-03
- 变更类型：架构
- 影响范围：Agent 持久化协议、流式事件目录、基础设施契约测试和项目文档

## 背景

当前 HTTP API 只实时发送 SSE 事件，不持久化事件历史，也没有断线续传订阅接口。内存事件总线和重放入口没有接入生产链路，与数据库设计说明不一致。

## 变更内容

- 删除未使用的 `EventBus` 协议、`MemoryEventBus` 实现和 `EventReplay` 包装模块。
- 删除当前没有消费者的 `CheckpointProvider` 协议。
- 删除仅覆盖内存事件重放骨架的契约测试。
- 保留当前流式发布所需的 `EventSequence` 和 SSE 编码。
- 更新 README 与架构文档，说明事件历史不持久化且当前不支持断线续传。

## 涉及文件

- `backend/agent/persistence/interfaces.py`：删除事件总线协议。
- `backend/agent/persistence/interfaces.py`：删除未使用的 CheckpointProvider 协议。
- `backend/agent/persistence/memory.py`：删除内存事件总线。
- `backend/agent/streaming/replay.py`：删除未接入的重放入口。
- `backend/tests/test_infrastructure_contracts.py`：移除对应的重放测试。
- `README.md`、`docs/ARCHITECTURE.md`、`CHANGELOG.md`：同步当前能力说明。

## 设计决策

- 当前没有事件持久化和订阅用例，因此不保留模拟 Redis 重放的空架构；需要断线续传时再按实际持久化和鉴权要求设计。
- 保留 `MemoryEventSequence`，它仍用于当前进程内为 SSE 事件生成游标。

## 测试与验证

- 命令：`python -m compileall -q backend`
- 结果：失败；系统 Python 递归扫描 `backend/.venv`，用较旧解释器解析项目依赖语法。
- 命令：`backend/.venv/Scripts/python.exe -m compileall -q agent app infra main.py tests`（在 `backend/` 目录执行）
- 结果：通过。
- 命令：`rg -n "EventBus|EventReplay|MemoryEventBus|streaming/replay\\.py|断点重放|重放历史|事件重放历史" README.md docs/ARCHITECTURE.md docs/数据库表结构.md backend`
- 结果：未发现已删除能力的遗留引用。
- 命令：`git diff --check`
- 结果：通过。
- 未运行自动化测试：本次删除的是未接入生产链路的重放脚手架。

## 潜在影响

- 不再提供内存事件历史重放；这与当前 API 和数据库设计一致。
- 以后实现 SSE 断线续传时，需要重新引入持久化事件存储、订阅接口和相应测试。

## 后续事项

- 无。
