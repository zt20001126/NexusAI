"""求职智能体的工具注册与接入能力。"""

from agents.job_agent.tools.ask_user_questions import (
    JobAgentQuestion,
    JobAgentQuestionPayload,
    ask_user_questions,
)
from agents.job_agent.tools.registry import ToolRegistry
from agents.job_agent.tools.recommend_job_roles import recommend_job_roles

__all__ = [
    "JobAgentQuestion",
    "JobAgentQuestionPayload",
    "ToolRegistry",
    "ask_user_questions",
    "recommend_job_roles",
]
