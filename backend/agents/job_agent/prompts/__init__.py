"""求职智能体提示词入口。"""

from agents.job_agent.prompts.loader import load_job_system_prompt

JOB_SYSTEM_PROMPT = load_job_system_prompt()

__all__ = ["JOB_SYSTEM_PROMPT"]
