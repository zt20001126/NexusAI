# 重组前端聊天功能结构

- 日期：2026-10-03
- 变更类型：架构
- 影响范围：前端聊天页面、会话状态管理、API 模块与项目目录文档

## 背景

前端原有 `pages/`、`components/` 和 `api/` 按技术类型分层，聊天页面同时负责页面展示、会话状态、请求编排和 SSE 事件处理。项目将持续扩展，需要让功能代码和共享基础能力有明确归属。

## 变更内容

- 将聊天页面、组件、API、状态 hook 和视图模型归入 `frontend/src/features/chat/`。
- 将 JSON 与 SSE 通用传输能力移入 `frontend/src/shared/api/`，并使 SSE 传输使用泛型事件类型。
- 将会话加载、发送、恢复、取消和 SSE 事件状态更新从页面提取到 `useChatSession`。
- 将消息视图模型及接口消息转换移入聊天功能的 `model/`。
- 在根 README 中说明前端目录结构和代码归属约定，并更新项目 changelog。

## 涉及文件

- `frontend/src/features/chat/`：承载聊天页面、专属组件、API、状态编排和视图模型。
- `frontend/src/shared/api/http.ts`：提供共享 JSON 与 SSE 传输，不再依赖 Agent 事件类型。
- `frontend/src/App.tsx`：更新聊天页面入口路径。
- `README.md`：记录前端目录职责及新增功能的归属原则。
- `CHANGELOG.md`：增加未发布架构调整摘要。

## 设计决策

- 采用按功能归组的结构，避免新增页面后继续扩大顶层通用目录。
- 只将跨功能的 HTTP/SSE 传输放入 `shared/`；聊天业务类型仍留在聊天功能内。
- 页面保留输入框草稿和 UI 组合，异步流程和会话状态由 `useChatSession` 封装。

## 测试与验证

- 命令：`npm run build`（在 `frontend/` 目录执行）
- 结果：TypeScript 检查通过，Vite 生产构建成功。
- 命令：`git diff --check`
- 结果：通过；Git 仅提示工作区 LF 文件在后续操作时可能转换为 CRLF。
- 未运行单元测试：前端 `package.json` 未配置测试脚本。

## 潜在影响

- 前端模块导入路径已调整，后续新增功能应遵循 README 中的功能归组约定。
- 暂无已知运行行为变化。

## 后续事项

- 无。
