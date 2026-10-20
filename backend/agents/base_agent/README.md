# 智能体基座

`base_agent` 为后续业务智能体提供独立的 LangGraph 运行骨架。它只依赖基础框架，不导入 `common_agent`、`research_agent` 等业务实现，也不管理数据库、模型 Provider 或外部客户端。

## 节点流程

```text
START → input_node → agent_node
                         ├─ 普通工具调用 → tool_node → agent_node
                         ├─ 提问工具调用 → tool_node → END（Runner 等待用户作答）
                         └─ 无工具调用   → output_node → END
```

四个节点始终参与图构建。工具集为空时模型不会绑定工具，正常流程直接从 `agent_node` 进入 `output_node`。

| 节点 | 输入与输出 | 职责 |
|---|---|---|
| `input_node` | 图状态 → 校验通过 | 检查最新用户消息类型、空白内容和长度，不向状态写入未使用的数据。 |
| `agent_node` | 对话状态 → 新 AI 消息 | 使用注入的模型和系统提示词；有工具时允许模型选择已注册工具。 |
| `tool_node` | AI 工具调用 → 工具消息 | 执行注册工具；普通工具结果返回模型继续处理，提问工具结果结束本阶段并交给 Runner 等待用户作答。失败时返回统一错误观察。 |
| `output_node` | 最后一条 AI 消息 → `answer` | 提取最终文本并校验非空，不发起第二次模型调用。 |

## 初始化边界

组合方创建模型、业务工具和可选 Checkpointer 后传入 `BaseAgent`。基座在初始化时检查工具名称、描述和参数 schema，并只构建一次已编译图。请求配置通过 `RunnableConfig` 传入；启用 Checkpointer 时必须提供 `configurable.thread_id`。

基座也提供一个带通用单选提问工具的基础对话助手工厂。该工具仅在用户明确要求题卡，或缺少会实质改变结果的关键选择时调用；普通开放式澄清仍使用自然语言。每批题卡有 1–3 道单选题，每次运行最多 3 轮；每题固定 4 个 `{label, description}` 选项，不允许自定义输入。题目结构复用共享追问协议，但该工具的入参 schema 将题型限制为 `SingleChoice`，不改变其他智能体的多选能力。

默认提示词按以下结构维护，由 `prompts/loader.py` 组合 `system.md` 与 `agent.md`。系统提示词定义助手身份与范围；Agent 行为指令约定交流方式、信息可靠性、提问工具触发条件、上下文和用户材料处理。模型仍由应用通过 Provider 创建并注入：

```text
prompts/
├── system.md  # 系统提示词
├── agent.md   # Agent 行为指令
└── loader.py  # 提示词加载器
```

```python
from langgraph.checkpoint.memory import MemorySaver
from agents.base_agent import create_basic_conversation_agent

assistant = create_basic_conversation_agent(
    agent="basic_conversation_agent",
    chat_model=chat_model,
    checkpointer=MemorySaver(),
)
runnable_config = {"configurable": {"thread_id": "user-id:basic_conversation_agent:conversation-id"}}
response = await assistant.ainvoke("你好，请介绍一下你自己。", runnable_config=runnable_config)
```

基础对话助手工厂要求注入 Checkpointer，并在同一会话的连续调用中复用同一个 `configurable.thread_id`。`MemorySaver` 适用于本地示例和短期进程内运行，进程重启后会丢失上下文；应用运行时使用 PostgreSQL Checkpointer，按用户、智能体和会话隔离并持久化历史。此工厂可在 Python 中直接调用；接入项目聊天界面时，由应用组合层注册并交给现有 Runner。

```python
agent = BaseAgent(
    config=BaseAgentConfig(
        agent="example_agent",
        system_prompt="在这里传入该业务智能体的系统提示词。",
    ),
    chat_model=chat_model,  # 由应用的模型 Provider 创建后注入
    tools=tools,            # 没有工具时省略
    checkpointer=checkpointer,
)
runnable_config = {"configurable": {"thread_id": "user-id:example_agent:conversation-id"}}
response = await agent.ainvoke("用户消息", runnable_config=runnable_config)
```

`AgentResponse.status` 为 `completed` 时读取 `answer`；为 `waiting` 时读取 `questions`，由直接调用方展示题目并把用户选择作为同一 `thread_id` 的下一条消息传回。产品聊天路径由共享 Runner 保存题卡、发出 `end(waiting)`，并通过现有恢复 API 校验答案后恢复同一 run。响应不会暴露工具调用、Checkpoint 状态或内部异常。外层平台若需要直接接入 LangGraph，可使用 `compiled_graph`。

## 新增工具

业务智能体在自己的 `tools/` 目录定义带有 Pydantic 参数 schema 和清晰描述的 LangChain `@tool`，通过工具工厂注入所需客户端或 Service，再将创建好的工具传入 `BaseAgent`。基础对话工厂默认注册 `ask_user_questions`；自定义 `BaseAgent` 可按需显式注入。工具返回值为简单结果时可使用字符串；结构化结果应由业务工具按 Pydantic schema 校验后再序列化。基座不创建工具依赖，也不在节点中读取环境变量。

```python
@tool("lookup_item", args_schema=LookupItemInput)
async def lookup_item(item_id: str) -> str:
    """按业务标识查询一条记录。"""
    return await injected_service.lookup(item_id)
```

工具名称必须唯一，并匹配小写字母、数字和下划线格式。工具执行异常不会带原始异常文本返回用户；基座会将受控错误观察交还给模型，最终回答仍由 `output_node` 校验。

## 扩展原则

- 业务节点、提示词、工具和领域类型放在具体智能体目录，不写入本基座。
- 基础对话提示词分为 `prompts/system.md` 和 `prompts/agent.md`，由 `prompts/loader.py` 加载；业务智能体应使用自己的提示词，避免修改基座默认行为。
- 模型、工具、Checkpointer 由组合根创建并注入；节点只消费依赖。
- 图状态只保存可序列化业务数据，不保存连接、客户端或密钥。
- 新增智能体可直接调用基座；接入产品 API 时再由应用组合层注册，不要求重构已有智能体。
