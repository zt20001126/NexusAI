"""智能体基座的工具注册与接入能力。"""

from agents.base_agent.tools.ask_user_questions import (
    BaseAgentQuestion,
    BaseAgentQuestionPayload,
    ask_user_questions,
)
from agents.base_agent.tools.registry import ToolRegistry

__all__ = [
    "BaseAgentQuestion",
    "BaseAgentQuestionPayload",
    "ToolRegistry",
    "ask_user_questions",
]
