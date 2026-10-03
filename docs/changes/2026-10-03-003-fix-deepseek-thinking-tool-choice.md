# 修复 DeepSeek Thinking 模式下的工具选择错误

- 日期：2026-10-03
- 变更类型：缺陷修复
- 影响范围：智能体对话中的模型工具选择

## 背景

DeepSeek Thinking 模式不支持 `tool_choice="required"`。智能体每次调用模型时都强制要求调用工具，导致模型 API 返回 400。

## 变更内容

- 移除强制工具选择参数，保留工具绑定并交由模型按需选择。
- 模型现在可以直接回复，也可以在需要时调用已登记工具。

## 涉及文件

- `backend/agent/nodes/agent_node.py`：工具绑定改为自动选择。
- `CHANGELOG.md`：记录未发布的缺陷修复。

## 设计决策

- 基础对话需要允许模型直接作答；自动工具选择同时兼容普通回答和工具调用。

## 测试与验证

- 未运行测试：本次请求未要求测试。
- 命令：`docker compose --env-file .env -f compose.yaml up -d --build --force-recreate backend`
- 结果：镜像构建成功，backend 容器已启动；容器日志显示应用启动完成。
- 代码差异和变更记录已检查。

## 潜在影响

- 模型可能直接回答而不调用工具，符合基础对话预期。

## 后续事项

- 通过前端发起对话确认 DeepSeek 请求不再返回该 400 错误。
