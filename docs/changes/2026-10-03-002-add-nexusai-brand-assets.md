# 接入 NexusAI 品牌标志

- 日期：2026-10-03
- 变更类型：新功能 / 文档
- 影响范围：前端品牌展示、浏览器标签页图标、项目 README

## 背景

项目提供了横版和图形版两份 NexusAI 标志，需要在前端合理位置使用，并让浏览器标签页显示不含文字的图标。

## 变更内容

- 将横版标志命名为 `nexusai-logo.png`，将无文字图形标志命名为 `nexusai-icon.png`，统一放入 `frontend/public/brand/`。
- 使用横版标志展示于 README，并在前端侧栏和移动端界面使用图形版。
- 将图形版设置为浏览器标签页图标；处理原图中嵌入的棋盘格背景为透明背景。

## 涉及文件

- `frontend/public/brand/nexusai-logo.png`：项目横版标志。
- `frontend/public/brand/nexusai-icon.png`：透明背景的浏览器与界面图标。
- `frontend/index.html`：配置 PNG favicon。
- `frontend/src/components/ConversationSidebar.tsx`：侧栏使用图形版标志。
- `frontend/src/pages/ChatPage.tsx`：移动端顶部使用图形版标志。
- `frontend/src/index.css`：调整图标尺寸和展示样式。
- `README.md`：展示横版标志。
- `CHANGELOG.md`：新增未发布摘要。
- `docs/changes/2026-10-03-002-add-nexusai-brand-assets.md`：本任务记录。

## 设计决策

- 将原图放在 Vite `public/brand/` 目录，便于 HTML favicon 和前端静态路径直接引用。
- 只有图形标志用于 favicon；含字标志用于网页品牌展示与 README。

## 测试与验证

- 命令：`npm run build`（在 `frontend/` 目录执行）。
- 结果：通过；TypeScript 检查和 Vite 生产构建均成功。
- 命令：`git diff --check`。
- 结果：通过；未发现空白错误。
- 命令：Python Pillow 图片检查（检查两张 PNG 的模式、尺寸和 alpha 范围）。
- 结果：两张图均为 RGBA PNG，均包含透明像素；横版图为 1849 × 851，图形版为 1268 × 1240。

## 潜在影响

- 浏览器可能缓存旧 favicon；刷新或清除站点缓存后可看到新图标。

## 后续事项

- 无。
