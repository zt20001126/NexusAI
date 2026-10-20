"""唯一智能体的工具清单。"""

from agent.constants import ASK_USER_QUESTIONS_TOOL_NAME
from agent.tools.example_tool import summarize_goal
from agent.tools.list_project_agents import list_project_agents

# 新业务只需在这里显式登记工具；这不是智能体注册中心。
AGENT_TOOLS = [summarize_goal, list_project_agents]
PAUSE_TOOL_NAMES = frozenset(
    {
        "ask_image_parameters",
        "ask_listing_questions",
        ASK_USER_QUESTIONS_TOOL_NAME,
    }
)
