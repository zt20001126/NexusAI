# 修复对话页面未显示当前智能体头像

- 日期：2026-10-16
- 变更类型：缺陷修复
- 影响范围：聊天欢迎区和最近会话侧栏中的智能体头像

## 背景

聊天欢迎区仍显示固定品牌图片，最近会话列表仍显示圆点；这两处都没有显示对应会话的智能体头像。

## 变更内容

- 欢迎区改为显示当前选中智能体的头像。
- 最近会话列表改为按每条会话的 `agent_id` 显示相应头像，并保留当前会话的高亮边框。
- 新增渲染级回归测试，检查欢迎区和侧栏都使用对应的共享头像组件。

## 涉及文件

- `frontend/src/features/chat/components/MessageList.tsx`：欢迎区使用当前智能体头像。
- `frontend/src/features/chat/components/ConversationSidebar.tsx`：按会话智能体 ID 渲染头像。
- `frontend/src/index.css`：调整侧栏头像尺寸和选中态样式。
- `frontend/tests/agentAvatars.test.mjs`：增加欢迎区与侧栏头像回归测试。
- `CHANGELOG.md`：记录未发布的缺陷修复。

## 设计决策

- 复用现有 `AgentAvatar` 组件，继续使用 `agent_id` 本地生成稳定头像，避免引入额外图片路径或网络请求。

## 测试与验证

- 命令：`npm test`（工作目录：`frontend/`，修改前运行）
- 结果：新回归测试按预期失败，分别指出欢迎区和会话项没有渲染对应智能体头像。
- 命令：`npm test`（工作目录：`frontend/`，修改后运行）
- 结果：通过，4 项测试通过，0 项失败。
- 命令：`npm run build`（工作目录：`frontend/`）
- 结果：TypeScript 检查及 Vite 生产构建通过；Vite 提示 JavaScript chunk 超过 500 kB。
- 命令：`git diff --check`
- 结果：通过，无空白错误。

## 潜在影响

- 侧栏会话图标从 10 px 圆点调整为 28 px 头像；选中态改用青色边框和光晕提示。

## 后续事项

- 无。
