# 智能体基座

`base_agent` 为后续业务智能体提供独立的 LangGraph 运行骨架。它只依赖基础框架，不导入 `common_agent`、`research_agent` 等业务实现，也不管理数据库、模型 Provider 或外部客户端。

## 节点流程

```text
START → validation_node → chat_node
                               ├─ 有已注册工具调用 → tool_node → chat_node
                               └─ 无工具调用       → answer_node → END
```

四个节点始终参与图构建。工具集为空时模型不会绑定工具，正常流程直接从 `chat_node` 进入 `answer_node`。

| 节点 | 输入与输出 | 职责 |
|---|---|---|
| `validation_node` | 图状态 → 规范化请求文本 | 检查最新用户消息类型、空白内容和长度。 |
| `chat_node` | 对话状态 → 新 AI 消息 | 使用注入的模型和系统提示词；有工具时允许模型选择已注册工具。 |
| `tool_node` | AI 工具调用 → 工具消息 | 执行注册工具；失败时返回统一错误观察供模型判断后续步骤。 |
| `answer_node` | 最后一条 AI 消息 → `answer` | 提取最终文本并校验非空，不发起第二次模型调用。 |

## 初始化边界

组合方创建模型、业务工具和可选 Checkpointer 后传入 `BaseAgent`。基座在初始化时检查工具名称、描述和参数 schema，并只构建一次已编译图。请求配置通过 `RunnableConfig` 传入；启用 Checkpointer 时必须提供 `configurable.thread_id`。

```python
agent = BaseAgent(
    config=BaseAgentConfig(
        agent_id="example_agent",
        system_prompt="在这里传入该业务智能体的系统提示词。",
    ),
    chat_model=chat_model,  # 由应用的模型 Provider 创建后注入
    tools=tools,            # 没有工具时省略
    checkpointer=checkpointer,
)
response = await agent.ainvoke("用户消息")
```

返回值是 `AgentResponse`，只包含稳定的 `agent_id` 和 `answer`，不会把工具调用、Checkpoint 状态或内部异常暴露给业务调用方。外层平台若需要直接接入 LangGraph，可使用 `compiled_graph`。

## 新增工具

业务智能体在自己的 `tools/` 目录定义带有 Pydantic 参数 schema 和清晰描述的 LangChain `@tool`，通过工具工厂注入所需客户端或 Service，再将创建好的工具传入 `BaseAgent`。工具返回值为简单结果时可使用字符串；结构化结果应由业务工具按 Pydantic schema 校验后再序列化。基座不创建工具依赖，也不在节点中读取环境变量。

```python
@tool("lookup_item", args_schema=LookupItemInput)
async def lookup_item(item_id: str) -> str:
    """按业务标识查询一条记录。"""
    return await injected_service.lookup(item_id)
```

工具名称必须唯一，并匹配小写字母、数字和下划线格式。工具执行异常不会带原始异常文本返回用户；基座会将受控错误观察交还给模型，最终回答仍由 `answer_node` 校验。

## 扩展原则

- 业务节点、提示词、工具和领域类型放在具体智能体目录，不写入本基座。
- 模型、工具、Checkpointer 由组合根创建并注入；节点只消费依赖。
- 图状态只保存可序列化业务数据，不保存连接、客户端或密钥。
- 新增智能体可直接调用基座；接入产品 API 时再由应用组合层注册，不要求重构已有智能体。
