# 修复图片智能体跨轮次沿用旧意图

- 日期：2026-10-14
- 变更类型：缺陷修复
- 影响范围：淘宝电商图片助手的多轮对话与生图意图识别

## 背景

图片智能体在同一会话中使用 LangGraph Checkpoint 保存状态。意图校验节点只检查持久化的 `intent_validated` 标记；用户第一轮发送普通文字后，该标记和非生图结果会被后续轮次复用，导致新的生图请求继续收到欢迎语。此外，关键词列表包含“详情页图”，未包含常见表达“详情图”。

## 变更内容

- 记录完成校验的 `run_id`，仅在同一个运行恢复时跳过重复校验；新运行重新识别意图。
- 新运行时清空上轮 `image_prompt`，避免下一张图片沿用旧提示词。
- 将“详情图”加入生图意图关键词。

## 涉及文件

- `backend/agents/image_generation/state.py`：记录经过校验的运行 ID。
- `backend/agents/image_generation/nodes/validation_node.py`：按运行轮次校验并识别“详情图”。
- `CHANGELOG.md`：记录未发布修复。

## 设计决策

- 新轮次由新的 `run_id` 识别；恢复同一轮追问时 `run_id` 不变，因此仍可保留已校验的生成上下文。

## 测试与验证

- 命令：`docker compose up -d --build backend`
- 结果：后端重新构建并启动成功，应用日志显示 startup complete。
- 验证：`GET /openapi.json` 返回 HTTP 200。
- 自动化测试及真实生图请求未运行。

## 潜在影响

- 暂无已知影响。

## 后续事项

- 无。
