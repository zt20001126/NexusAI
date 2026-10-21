"""验证求职智能体基础图及注册边界。"""

from langgraph.checkpoint.memory import MemorySaver

from agent.constants import JOB_AGENT
from agents.job_agent import create_job_agent
from agents.registry import PROJECT_AGENT_DEFINITIONS
from tests.fake_models import ScriptedToolCallingModel


async def test_job_agent_supports_registered_multi_turn_chat() -> None:
    """独立图可通过 Checkpointer 持续对话，并作为稳定类型出现在目录中。"""

    definition = next(item for item in PROJECT_AGENT_DEFINITIONS if item.agent == JOB_AGENT)
    assert definition.name == "求职助手"

    assistant = create_job_agent(
        agent=JOB_AGENT,
        chat_model=ScriptedToolCallingModel(),
        checkpointer=MemorySaver(),
    )
    assert "ask_user_questions" in assistant.tool_registry.names

    config = {"configurable": {"thread_id": "job-agent-chat-test"}}
    first = await assistant.ainvoke("我想找后端工程师岗位。", runnable_config=config)
    second = await assistant.ainvoke("我有三年开发经验。", runnable_config=config)

    assert first.status == "completed"
    assert second.status == "completed"
    assert first.agent == JOB_AGENT
    assert second.agent == JOB_AGENT
