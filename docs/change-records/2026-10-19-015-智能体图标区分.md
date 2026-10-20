# 保留不同智能体的头像差异

- 日期：2026-10-19
- 变更类型：缺陷修复
- 影响范围：智能体市场、智能体选择弹窗、会话列表和聊天消息头像

## 背景

当前前端按字符串枚举 `agent` 读取智能体类型，但运行中的 API 仍以旧字段 `agent_id` 返回相同的字符串枚举值。字段不匹配使头像组件收到 `undefined`，所有头像因此命中同一个缓存项。迁移时 seed 也曾从旧雪花 ID 改成枚举字符串，改变了生成的头像图案。

## 变更内容

- 在智能体目录和会话列表 API 边界兼容 `agent` 与 `agent_id` 两种字段名，并统一转换为已知 `AgentType`；未知类型会显示加载错误，不再静默共用头像。
- 按 `AgentType` 建立穷举的固定 seed 映射，恢复原先各智能体使用的头像图案。
- `AgentAvatar` 在市场、选择弹窗、会话列表和消息区显示同一智能体对应的稳定头像。
- 明确头像 seed 仅用于前端生成视觉，不作为 API 或数据库字段。

## 涉及文件

- `frontend/src/features/chat/constants.ts`：统一校验和转换智能体类型。
- `frontend/src/features/chat/api/agent.ts`：规范化智能体目录响应。
- `frontend/src/features/chat/api/conversations.ts`：规范化会话列表响应。
- `frontend/src/features/chat/components/AgentAvatar.tsx`：增加类型到固定头像 seed 的映射。
- `frontend/src/index.css`：为共享头像图片统一设置尺寸。
- `CHANGELOG.md`：更新未发布变更摘要。

## 设计决策

- 保留现有 DiceBear Bottts 风格和历史 seed，使标识字段迁移不会改变已有头像外观；当前后端和 API 契约仍以字符串 `agent` 为准。
- 使用 `Record<AgentType, string>` 保证新增智能体时必须补充头像 seed。

## 测试与验证

- 命令：读取 `http://localhost:5173/api/agents` 和 `http://localhost:5173/api/conversations?limit=1&offset=0`。
- 结果：运行中的 API 返回旧字段名 `agent_id`，其值仍是字符串枚举；这与前端原先只读取 `agent` 的实现不匹配。
- 命令：`git diff --check`
- 结果：通过。
- 未运行自动化测试或构建；本次请求未要求执行自动化测试或构建。

## 潜在影响

- 暂无已知影响。

## 后续事项

- 无。
