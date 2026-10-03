# 渲染助手 Markdown 回复

- 日期：2026-10-03
- 变更类型：缺陷修复
- 影响范围：前端对话消息展示

## 背景

助手回复会包含 Markdown 标记，但消息列表此前将其作为普通字符串展示，导致 `**` 等标记直接出现在页面中。

## 变更内容

- 助手消息改用 `react-markdown` 与 `remark-gfm` 渲染常见 Markdown 和 GFM 内容。
- 为段落、标题、列表、引用、链接、表格、图片和代码块增加与现有主题一致的样式。
- 用户消息继续作为纯文本展示并保留换行；Markdown 中的原始 HTML 不启用。
- Markdown 链接在新标签页打开。

## 涉及文件

- `frontend/src/components/MessageList.tsx`：区分渲染助手 Markdown 与用户纯文本。
- `frontend/src/index.css`：增加助手 Markdown 内容排版样式。
- `frontend/package.json`、`frontend/package-lock.json`：添加 Markdown 渲染依赖。
- `CHANGELOG.md`：记录面向使用者的变化。

## 设计决策

- Markdown 只应用于助手回复，避免改变用户消息文本的呈现。
- 使用 React Markdown 组件渲染，不将模型文本写入 `dangerouslySetInnerHTML`。

## 测试与验证

- 命令：`npm run build`（在 `frontend/` 目录执行）
- 结果：TypeScript 检查和 Vite 生产构建通过。
- 命令：`git diff --check`
- 结果：通过；Git 提示已有 LF 文件在 Windows 工作副本中可能转换为 CRLF。

## 潜在影响

- 前端生产包包含 Markdown 渲染相关依赖。

## 后续事项

- 无。
