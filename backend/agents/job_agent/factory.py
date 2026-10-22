"""提供求职助手的构造入口。"""

from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.enums import AgentType
from agents.job_agent.agent import JobAgent
from agents.job_agent.config import JobAgentConfig
from agents.job_agent.prompts import JOB_SYSTEM_PROMPT
from agents.job_agent.resume_snapshot import JobResumeSnapshot
from agents.job_agent.tools.ask_user_questions import ask_user_questions
from agents.job_agent.tools.recommend_job_roles import recommend_job_roles
from agents.job_agent.tools.read_saved_resume import create_read_saved_resume_tool
from agents.job_agent.tools.stage_resume_optimization import stage_resume_optimization


def create_job_agent(
    *,
    chat_model: BaseChatModel,
    agent: AgentType = AgentType.JOB,
    checkpointer: BaseCheckpointSaver[Any],
    resume_reader: Callable[[], JobResumeSnapshot] | None = None,
    resume_optimization_writer: Callable[[dict], str] | None = None,
) -> JobAgent:
    """创建带结构化追问与岗位推荐能力的求职对话图。"""

    tools: list[BaseTool] = [ask_user_questions, recommend_job_roles]
    if resume_reader is not None:
        tools.append(create_read_saved_resume_tool(resume_reader))
        tools.append(stage_resume_optimization)

    return JobAgent(
        config=JobAgentConfig(
            agent=agent,
            system_prompt=JOB_SYSTEM_PROMPT,
        ),
        chat_model=chat_model,
        tools=tools,
        checkpointer=checkpointer,
        resume_optimization_writer=resume_optimization_writer,
    )
