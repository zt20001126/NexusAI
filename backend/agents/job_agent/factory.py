"""提供求职助手的构造入口。"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.enums import AgentType
from agents.job_agent.agent import JobAgent
from agents.job_agent.config import JobAgentConfig
from agents.job_agent.prompts import JOB_SYSTEM_PROMPT
from agents.job_agent.tools.ask_user_questions import ask_user_questions
from agents.job_agent.tools.recommend_job_roles import recommend_job_roles


def create_job_agent(
    *,
    chat_model: BaseChatModel,
    agent: AgentType = AgentType.JOB,
    checkpointer: BaseCheckpointSaver[Any],
) -> JobAgent:
    """创建带结构化追问与岗位推荐能力的求职对话图。"""

    return JobAgent(
        config=JobAgentConfig(
            agent=agent,
            system_prompt=JOB_SYSTEM_PROMPT,
        ),
        chat_model=chat_model,
        tools=[ask_user_questions, recommend_job_roles],
        checkpointer=checkpointer,
    )
