"""提供可直接调用的基础对话助手构造入口。"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from agents.base_agent.agent import BaseAgent
from agents.base_agent.config import BaseAgentConfig
from agents.base_agent.prompts import DEFAULT_CHAT_SYSTEM_PROMPT


DEFAULT_BASIC_AGENT_ID = "basic_conversation_agent"


def create_basic_conversation_agent(
    *,
    chat_model: BaseChatModel,
    agent_id: str = DEFAULT_BASIC_AGENT_ID,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> BaseAgent:
    """创建不带工具的基础对话助手；模型与可选持久化器由调用方注入。"""

    return BaseAgent(
        config=BaseAgentConfig(
            agent_id=agent_id,
            system_prompt=DEFAULT_CHAT_SYSTEM_PROMPT,
        ),
        chat_model=chat_model,
        checkpointer=checkpointer,
    )
