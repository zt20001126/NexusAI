# 聊天消息使用图片头像

- 日期：2026-10-16
- 变更类型：其他
- 影响范围：前端聊天消息中的智能体和用户头像

## 背景

`frontend/public` 中提供了智能体与用户的头像图片，需要在项目中使用并集中存放。

## 变更内容

- 新建 `frontend/public/avatars/`，将 `agent.png` 和 `user.png` 放入其中。
- 聊天消息的智能体头像改用 `/avatars/agent.png`，用户头像改用 `/avatars/user.png`。
- 智能体和用户头像容器均使用白色背景，用户头像样式适配图片资源。

## 涉及文件

- `frontend/public/avatars/agent.png`：存放智能体头像。
- `frontend/public/avatars/user.png`：存放用户头像。
- `frontend/src/features/chat/components/MessageList.tsx`：引用头像图片。
- `frontend/src/index.css`：设置用户头像图片样式。
- `CHANGELOG.md`：记录未发布的头像变更。

## 设计决策

- 将头像放在 Vite `public` 目录下的 `avatars` 子目录，以 `/avatars/...` 静态路径引用。
- 两个头像容器均使用白色背景；图片使用 `object-fit: contain`，保留透明头像图片的完整画面。

## 测试与验证

- 命令：`npm run build`
- 结果：通过；TypeScript 检查和 Vite 生产构建均成功。
- 命令：`npm test`
- 结果：通过；1 项测试通过，0 项失败。

## 潜在影响

- 暂无已知影响。

## 后续事项

- 无。
