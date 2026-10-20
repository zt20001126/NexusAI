# 新增智能体目录介绍页

- 日期：2026-10-16
- 变更类型：新功能
- 影响范围：前端聊天导航和智能体发现流程

## 背景

智能体目前只在开启新对话时通过弹窗展示，用户缺少一个可随时浏览全部智能体和了解其用途的入口。

## 变更内容

- 将侧栏 NexusAI 品牌区设为智能体目录入口；手机端聊天顶部品牌图标也可打开目录。
- 在右侧主区域展示后端已注册智能体的头像、名称、简介和支持能力，并提供加载、错误、空列表状态及重试操作。
- 点击智能体卡片后切换到对应的新对话；打开目录期间保留聊天界面挂载状态，侧栏会话列表继续可用。
- 有当前会话时提供返回当前对话的入口，便于在手机端回到聊天。

## 涉及文件

- `frontend/src/features/chat/ChatPage.tsx`：协调目录、聊天和会话选择状态。
- `frontend/src/features/chat/components/AgentDirectory.tsx`：展示智能体目录及列表状态。
- `frontend/src/features/chat/components/ConversationSidebar.tsx`：添加品牌区目录入口。
- `frontend/src/index.css`：添加目录卡片、状态、焦点和响应式样式。
- `CHANGELOG.md`：汇总未发布功能。

## 设计决策

- 使用现有 `/api/agents` 数据源和头像组件，确保目录与后端注册目录一致。
- 目录只替换右侧聊天显示；聊天工作区保持挂载以保留输入和面板状态。

## 测试与验证

- 命令：`npm run build`（在 `frontend/` 执行）
- 结果：TypeScript 检查通过，Vite 成功构建。
- 命令：`git diff --check`
- 结果：通过。
- 未运行 `npm test`；本次完成构建检查，未额外运行测试套件。

## 潜在影响

- 构建工具提示主 JavaScript chunk 超过 500 kB；构建成功，此提示不影响本次功能使用。

## 后续事项

- 无。
