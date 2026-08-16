"""唯一智能体的工具清单。"""

from agent.tools.ask_user_question import ask_user_question
from agent.tools.example_tool import summarize_goal

# 新业务只需在这里显式登记工具；这不是智能体注册中心。
AGENT_TOOLS = [ask_user_question, summarize_goal]
PAUSE_TOOL_NAMES = frozenset({"ask_user_question"})
