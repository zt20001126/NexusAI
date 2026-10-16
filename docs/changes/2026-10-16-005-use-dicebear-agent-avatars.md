# 为智能体生成一致的机器人头像

- 日期：2026-10-16
- 变更类型：新功能
- 影响范围：智能体选择弹窗、聊天消息中的智能体头像

## 背景

智能体选择弹窗使用相同的星形图标，聊天消息则使用固定的助手头像。随着可选智能体增加，两处都需要显示能区分智能体且相互一致的机器人头像。

## 变更内容

- 接入 DiceBear `Bottts` 风格，使用智能体 `agent_id` 作为 seed，在浏览器本地生成稳定的 SVG 机器人头像。
- 新增共享的 `AgentAvatar` 组件，选择弹窗和聊天消息均使用它；同一个智能体在两个位置显示相同头像。
- 头像按 API 返回的 ID 自动生成，不维护逐个智能体的静态映射；新增智能体可直接获得头像。

## 涉及文件

- `frontend/package.json`、`frontend/package-lock.json`：添加 DiceBear Core 10.7.0 和 Styles 10.6.0。
- `frontend/src/features/chat/components/AgentAvatar.tsx`：新增基于智能体 ID 的本地机器人头像生成组件。
- `frontend/src/features/chat/components/AgentSelectionDialog.tsx`：在智能体选择卡片中显示生成的机器人头像。
- `frontend/src/features/chat/components/MessageList.tsx`、`frontend/src/features/chat/ChatPage.tsx`：将当前会话智能体 ID 传入消息列表，并显示相同头像。
- `frontend/src/index.css`：调整选择卡片图标容器以适配生成的 SVG。
- `CHANGELOG.md`：在 `[Unreleased]` 记录智能体头像变化。

## 设计决策

- 使用 DiceBear JavaScript 库在浏览器本地生成 SVG，不调用第三方头像 API，也不把智能体 ID 发往外部服务。
- 以稳定的 `agent_id` 作为 seed，避免硬编码头像表，让未来注册的智能体自动得到固定头像。
- 使用 Bottts 机器人风格；DiceBear Core 使用 MIT 许可证，Bottts 风格注明可个人及商业使用，详见 [Bottts 许可说明](https://bottts.com/)。

## 测试与验证

- 命令：`npm test`（工作目录：`C:\Users\96598\.codex\worktrees\7ba4\NexusAI\frontend`）
- 结果：通过，1 项测试通过。
- 命令：`npm run build`（工作目录：`C:\Users\96598\.codex\worktrees\7ba4\NexusAI\frontend`）
- 结果：TypeScript 检查和 Vite 生产构建通过；Vite 提示生成的 JavaScript chunk 超过 500 kB。
- 命令：`npm test` 和 `npm run build`（工作目录：`E:\Agent\NexusAI\frontend`）
- 结果：测试 1 项通过，TypeScript 检查和 Vite 生产构建通过；Vite 同样提示 JavaScript chunk 超过 500 kB。
- 在 Edge 实际页面打开智能体选择弹窗，确认当前 5 个智能体生成 5 个不同头像；当前会话的“通用智能体”消息头像与选择卡片头像一致。
- 命令：`git diff --check`（工作目录：项目工作树）
- 结果：通过，无空白错误。

## 潜在影响

- DiceBear 生成器增加前端 JavaScript 体积；本地生产构建通过，但 Vite 对超过 500 kB 的 chunk 发出提示。
- 后续 DiceBear 版本升级可能改变同一 seed 生成的图案；当前版本由 lock 文件固定。

## 后续事项

- 无。
