"""示例智能体注册定义。"""

from agent_core.contracts.agent import AgentDefinition
from agents.example_agent.graph import create_example_graph
from agents.example_agent.state import ExampleAgentState


def create_example_agent_definition() -> AgentDefinition:
    """返回可注册的示例智能体定义。"""
    return AgentDefinition(
        agent_id="example",
        name="示例需求助手",
        description="演示结构化追问、工具调用和恢复执行",
        graph_factory=create_example_graph,
        pause_tool_names=frozenset({"ask_user_question"}),
        state_schema=ExampleAgentState,
        tool_names=frozenset({"ask_user_question", "summarize_goal"}),
        system_prompt="收集用户目标，调用工具整理后返回简洁结果。",
    )
