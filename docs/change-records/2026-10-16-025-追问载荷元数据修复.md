# 修复图片尺寸追问载荷校验

- 日期：2026-10-16
- 变更类型：缺陷修复
- 影响范围：图片智能体结构化追问和共享运行器

## 背景

图片智能体已生成尺寸选择问题并调用追问工具，但运行器返回“追问信息格式不正确”。追问工具将问题列表和 `task_result` 状态一并放入工具结果的 `data` 字段；运行器将整个 `data` 传给只允许 `questions` 字段的 `QuestionPayload`，因此严格校验把 `task_result` 当作额外字段拒绝。

## 变更内容

- 运行器只从工具结果中提取 `questions` 交给公共问题协议校验。
- 保留完整工具结果供后续处理，使 `task_result` 仍可发布为任务状态事件。

## 涉及文件

- `backend/agent/runner.py`：从暂停工具结果中单独校验问题列表。
- `CHANGELOG.md`：记录未发布缺陷修复。

## 设计决策

- 问题校验只约束问题列表；任务结果状态是同一工具结果中的独立元数据。

## 测试与验证

- 修复前命令：`backend/.venv/Scripts/python.exe -m pytest tests/test_api.py::test_image_agent_upload_ask_resume_persist_and_authorize_result -q`（在 `backend/` 目录执行）。
- 结果：失败；事件为 `INVALID_QUESTION_PAYLOAD`，校验错误指出 `task_result` 是额外字段。
- 修复后命令：同上。
- 结果：`1 passed`；上传参考图、尺寸追问、恢复生成和结果读取的 API 流程通过。
- 命令：`backend/.venv/Scripts/python.exe -m pytest tests/test_runtime.py::test_malformed_question_tool_result_fails_instead_of_waiting_forever -q`（在 `backend/` 目录执行）。
- 结果：`1 passed`；畸形追问载荷仍会被拒绝。
- 同批额外检查中的 Listing API 用例仍在 `ListingPlan` JSON 校验阶段失败；该失败发生于 Listing 计划节点，不经过本次修复的追问载荷校验路径。

## 潜在影响

- 使用共享暂停工具协议的智能体，其追问结果现在可以同时携带任务结果元数据。

## 后续事项

- 暂无。
