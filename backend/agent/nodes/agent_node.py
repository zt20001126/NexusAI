"""由 DeepSeek 驱动的工具决策节点。"""

from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage

from agent.prompts.system import SYSTEM_PROMPT
from agent.state import AgentState
from agent.tools.registry import AGENT_TOOLS


def create_agent_node(chat_model: BaseChatModel) -> Callable[..., Any]:
    """按需绑定已登记工具，允许模型直接回复或选择调用工具。"""
    model_with_tools = chat_model.bind_tools(AGENT_TOOLS)

    async def agent_node(state: AgentState) -> dict[str, list[BaseMessage]]:
        messages = list(state.get("messages", []))
        if not messages or not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=SYSTEM_PROMPT))
        response = await model_with_tools.ainvoke(messages)
        return {"messages": [response]}

    return agent_node
