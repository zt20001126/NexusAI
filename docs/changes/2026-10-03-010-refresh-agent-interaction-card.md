# 优化 Agent 对话交互卡片

- 日期：2026-10-03
- 变更类型：架构
- 影响范围：前端 Agent 补充信息交互卡片

## 背景

原 `QuestionForm` 将所有 Agent 问题固定渲染为 textarea，卡片信息层级较弱，且缺少其它交互题型的扩展结构。

## 变更内容

- 将组件重命名并重构为 `AgentInteractionCard`，支持文本题、单选题、多选题、确认题和文件选择题渲染。
- 兼容未提供题型标识的现有问题载荷，仍按文本题处理；恢复回调及现有 API 调用保持不变。
- 将卡片收窄至最大 740px，采用 24px 内边距、15px 圆角、白色背景和浅色描边。
- 调整标题、描述、问题和输入控件层级；文本框改为浅灰背景，聚焦时才显示品牌蓝描边和轻量焦点环。
- 将提交按钮调整为 40px 高度，并使用 NexusAI Navy / Blue 色系。
- 文件选择题目前将所选文件名作为答案文本提交；二进制上传需要后续扩展接口。

## 涉及文件

- `frontend/src/components/QuestionForm.tsx`：移除旧的 textarea 专用组件。
- `frontend/src/components/AgentInteractionCard.tsx`：新增按题型渲染的对话卡片。
- `frontend/src/api/agent.ts`：扩展前端问题题型定义，并兼容现有文本题数据。
- `frontend/src/pages/ChatPage.tsx`：切换到新卡片组件，保持原恢复回调。
- `frontend/src/index.css`：更新卡片布局及各题型控件样式。
- `CHANGELOG.md`：记录未发布变化。

## 设计决策

- 题型沿用 `type` 判别字段；缺少该字段时默认为文本题，保持与当前后端载荷兼容。
- 保持现有答案回调和恢复接口调用，以满足不改动业务状态及接口流程的要求。

## 测试与验证

- 命令：`npm run build`（在 `frontend/` 目录执行）
- 结果：TypeScript 检查和 Vite 生产构建通过。
- 命令：`git diff --check`
- 结果：通过。

## 潜在影响

- 文件选择题仅将文件名传给现有恢复流程，尚未上传文件内容。

## 后续事项

- 如需实际上传文件，需定义文件传输和恢复接口协议。
