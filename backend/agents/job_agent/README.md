# 求职智能体基础框架

`job_agent` 由 `base_agent` 的图、状态、节点、工具、Schema、错误和提示词结构复制而来，拥有独立实现目录。通过 `backend/bootstrap/runtime.py` 注入模型与 PostgreSQL Checkpointer，并复用共享 Agent Runner、会话、题卡和 SSE 协议。

## 当前能力

- 在同一会话中进行多轮求职相关对话。
- 需要关键选择时使用 `ask_user_questions` 单选题卡，等待用户作答后继续运行。
- 根据用户在对话中提供的岗位和经历信息给出基础建议。

当前没有简历读取或修改工具，也没有职位检索、投递和外部平台接入。提示词明确约束智能体不能声称已执行这些操作。

## 代码边界

`factory.py` 创建 `JobAgent`，`graph.py` 连接 `input_node → agent_node → tool_node/output_node`；`prompts/` 定义求职助手身份和行为；`tools/` 目前只包含结构化追问。业务工具以后放在本目录并通过工厂注入，不复制共享 Runner。
'
