# 在聊天消息中展示模型追问题卡

- 日期：2026-10-19
- 变更类型：界面与接口
- 影响范围：结构化追问消息、聊天时间线和会话历史

## 背景

模型生成的问题此前以一段普通助手文本保存，当前答题表单又显示在消息列表之外。题目、选项和用户回答因此不在同一条聊天时间线上。

## 变更内容

- 持久化完整追问批次、轮次和运行标识，让历史接口可以还原题目及选项。
- 将待回答表单嵌入对应助手消息卡片，提交后保留为只读的历史题卡。
- 加入追问事件与历史加载之间的临时题卡回退，避免等待历史请求时题卡暂时缺失。
- 在 API 文档中说明新增的 `question_batch` 内容块。

## 涉及文件

- `backend/agent/runner.py`、`backend/tests/test_api.py`：持久化并验证结构化追问批次。
- `frontend/src/features/chat/api/conversations.ts`、`frontend/src/features/chat/model/messages.ts`：扩展消息类型与展示模型。
- `frontend/src/features/chat/ChatPage.tsx`、`frontend/src/features/chat/components/MessageList.tsx`、`frontend/src/features/chat/components/AgentInteractionCard.tsx`、`frontend/src/index.css`：在时间线题卡中展示模型问题、选项和当前答题表单。
- `docs/API接口文档.md`、`CHANGELOG.md`：同步接口与变更摘要。

## 设计决策

- 继续保留助手文本块以兼容旧客户端；新版前端优先使用 `question_batch` 结构化内容。
- 活动题卡直接复用现有答案表单；历史题卡只读显示问题和选项，避免在列表外重复展示。
- `question_batch` 存在消息 JSON 内容中，不新增数据库列或迁移。

## 测试与验证

- 命令：`npm test`（工作目录：`frontend/`）
- 结果：10 项通过。
- 命令：`npm run build`（工作目录：`frontend/`）
- 结果：TypeScript 检查和生产构建通过；Vite 报告大 chunk 提示。
- 命令：`.venv/Scripts/python.exe -m pytest -q tests/test_api.py -k conversation_and_message_history_endpoints_support_paging`（工作目录：`backend/`）
- 结果：1 项通过，20 项因测试筛选未运行；有 1 条 Starlette `BlockingPortal` 弃用警告。
- 命令：`git diff --check`
- 结果：通过。

## 潜在影响

- 消息历史新增 `question_batch` 内容块；旧客户端可继续读取原有文本块。
- 仅此前未保存结构化题目的老消息无法还原历史选项；上线后新追问可完整展示。

## 后续事项

- 无。
