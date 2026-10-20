# 高亮当前选中会话圆点

- 日期：2026-10-16
- 变更类型：其他
- 影响范围：前端侧栏最近会话列表

## 背景

侧栏中的会话圆点此前都显示为弱化的空心符号，当前选中的会话不易通过圆点辨认。

## 变更内容

- 将会话圆点改为 CSS 绘制的空心圆。
- 为选中会话的圆点增加品牌青色填充和清晰可见的外圈光晕。

## 涉及文件

- `frontend/src/features/chat/components/ConversationSidebar.tsx`：移除圆点字符，保留装饰性图形容器。
- `frontend/src/index.css`：定义圆点基础样式及选中态样式。
- `CHANGELOG.md`：在 `[Unreleased]` 记录侧栏视觉优化。

## 设计决策

- 复用已有的 `is-active` 会话状态和品牌青色，无需增加新的状态逻辑。

## 测试与验证

- 命令：`npm test`（工作目录：`frontend`）
- 结果：通过，1 项测试通过。
- 命令：`npm ci`（工作目录：`frontend`）
- 结果：成功安装锁文件中定义的依赖。
- 命令：`npm run build`（工作目录：`frontend`）
- 结果：TypeScript 检查和 Vite 生产构建通过。
- 命令：`git diff --check`
- 结果：通过，无空白错误。

## 潜在影响

- 暂无已知影响。

## 后续事项

- 无。
