"""唯一智能体图的构建与路由。"""

from typing import Any, Literal

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from agent.nodes.agent_node import agent_node
from agent.nodes.result_node import result_node
from agent.nodes.validation_node import validation_node
from agent.state import AgentState
from agent.tools.registry import AGENT_TOOLS, PAUSE_TOOL_NAMES


def route_after_agent(state: AgentState) -> Literal["tools", "__end__"]:
    """模型请求工具时进入工具节点，直接回答时结束当前图执行。"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    return "tools" if getattr(last_message, "tool_calls", None) else END


def route_after_tools(state: AgentState) -> Literal["result", "__end__"]:
    """追问工具暂停本轮，普通业务工具进入结果节点。"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    return END if getattr(last_message, "name", None) in PAUSE_TOOL_NAMES else "result"


def build_agent_graph(checkpointer: Any) -> Any:
    """构建并编译唯一智能体；新增业务时主要扩展节点、工具和边。"""
    graph = StateGraph(AgentState)
    graph.add_node("validation", validation_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(AGENT_TOOLS))
    graph.add_node("result", result_node)
    graph.add_edge(START, "validation")
    graph.add_edge("validation", "agent")
    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_conditional_edges("tools", route_after_tools)
    graph.add_edge("result", END)
    compiled = graph.compile(checkpointer=checkpointer)
    compiled.pause_tool_names = PAUSE_TOOL_NAMES
    return compiled
