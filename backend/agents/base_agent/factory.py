"""提供可直接调用的基础对话助手构造入口。"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.enums import AgentType
from agents.base_agent.agent import BaseAgent
from agents.base_agent.config import BaseAgentConfig
from agents.base_agent.prompts import DEFAULT_CHAT_SYSTEM_PROMPT


def create_basic_conversation_agent(
    *,
    chat_model: BaseChatModel,
    agent: AgentType,
    checkpointer: BaseCheckpointSaver[Any],
) -> BaseAgent:
    """创建支持多轮上下文的基础对话助手；模型和持久化器由调用方注入。"""

    return BaseAgent(
        config=BaseAgentConfig(
            agent=agent,
            system_prompt=DEFAULT_CHAT_SYSTEM_PROMPT,
        ),
        chat_model=chat_model,
        checkpointer=checkpointer,
    )
