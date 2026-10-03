# 修复智能体回复流式输出

- 日期：2026-10-03
- 变更类型：缺陷修复
- 影响范围：后端 Agent 模型调用、最终回复节点和 SSE 消息事件

## 背景

虽然后端已经提供 SSE 和 `message.delta` 事件，但智能体节点使用 `ainvoke()` 等待完整模型响应。工具结果节点也直接构造完整回复，因此普通回复不会逐步到达前端。

## 变更内容

- 新增模型流式调用辅助函数，逐块消费模型输出并累积完整 `AIMessage`，兼顾后续工具路由和消息持久化。
- 智能体工具决策调用改用 `astream()`，Runner 转发 `agent` 和 `result` 节点的用户可见文本 chunk。
- 工具结果节点改为基于对话及工具结果调用无工具绑定的模型，流式生成最终回复。
- 对没有流式接口的轻量 Provider 保留 `ainvoke()` / 原有确定性结果回退；Runner 在完成事件时补发未通过流式通道到达的文本。
- 将 chunk 和最终消息按节点对齐，避免前端重复追加最终文本，并继续限制输出长度及持久化完整消息。

## 涉及文件

- `backend/agent/streaming/model.py`：模型 chunk 聚合与非流式 Provider 回退。
- `backend/agent/nodes/agent_node.py`：通过流式模型调用生成工具决策或直接答复。
- `backend/agent/nodes/result_node.py`：流式生成工具执行后的用户答复。
- `backend/agent/graph.py`：在图中注册流式结果节点。
- `backend/agent/runner.py`：转发可见节点增量、补齐未流出的最终文本并执行长度限制。
- `CHANGELOG.md`：在 `[Unreleased]` 中记录后端流式输出修复。

## 设计决策

- 工具调用需要完整累积 `AIMessageChunk` 后再由现有图路由处理；文本 token 则从 LangGraph `messages` 流独立发出。
- 工具结果使用无工具绑定模型生成用户答复，避免把工具调用参数混入最终回复。
- 没有 `astream()` 的测试替身或自定义轻量模型仍可使用原有完整响应回退。

## 测试与验证

- 命令：`py -3.11 -m py_compile backend/agent/streaming/model.py backend/agent/nodes/agent_node.py backend/agent/nodes/result_node.py backend/agent/graph.py backend/agent/runner.py`
- 结果：通过；所有修改的 Python 文件完成语法编译。
- 未运行 pytest；本次请求未要求运行测试。

## 潜在影响

- 工具执行完成后的用户答复现在会额外调用一次聊天模型，以流式自然语言总结工具结果。
- 对话直接答复仍使用同一次绑定工具的模型调用，工具调用行为保持不变。

## 后续事项

- 无。
