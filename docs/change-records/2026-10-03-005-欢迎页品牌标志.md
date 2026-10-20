# 欢迎页使用 NexusAI 品牌标志

- 日期：2026-10-03
- 变更类型：其他
- 影响范围：前端对话空状态欢迎页

## 背景

对话为空时，欢迎页中央显示的是星形装饰符号，与项目品牌标志不一致。

## 变更内容

- 将欢迎页中央的星形符号替换为现有 NexusAI 图标。
- 调整图标容器的底色、边框和阴影，使品牌图标在欢迎页中清晰居中。

## 涉及文件

- `frontend/src/components/MessageList.tsx`：欢迎区域加载 NexusAI 品牌图标。
- `frontend/src/index.css`：更新欢迎页品牌图标容器和图标尺寸样式。
- `CHANGELOG.md`：在 `[Unreleased]` 摘要中记录欢迎页图标更新。

## 设计决策

- 复用 `frontend/public/brand/nexusai-icon.png`，与侧栏及消息头像使用相同品牌资源。

## 测试与验证

- 命令：`npm run build`（在 `frontend/` 目录执行）
- 结果：通过；TypeScript 检查完成，Vite 生产构建成功。

## 潜在影响

- 暂无已知影响。

## 后续事项

- 无。
