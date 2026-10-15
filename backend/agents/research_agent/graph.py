"""科研文献检索智能体 LangGraph 组装。"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from agent.persistence.interfaces import TaskResultStore
from agents.research_agent.nodes.finalize import finalize_node
from agents.research_agent.nodes.plan import create_plan_node
from agents.research_agent.nodes.search import create_search_call_node
from agents.research_agent.providers.openalex_client import OpenAlexClient
from agents.research_agent.state import ResearchAgentState
from agents.research_agent.tools.search_works import create_research_search_tool


def build_research_agent_graph(
    checkpointer: Any,
    chat_model: BaseChatModel,
    openalex_client: OpenAlexClient,
    task_result_store: TaskResultStore,
    max_search_rounds: int,
) -> Any:
    """构建计划、检索工具和确定性回复图。"""
    search_tool = create_research_search_tool(
        openalex_client=openalex_client,
        task_result_store=task_result_store,
    )
    graph = StateGraph(ResearchAgentState)
    graph.add_node("plan_node", create_plan_node(chat_model))
    graph.add_node("search_call_node", create_search_call_node(max_search_rounds))
    graph.add_node("tool_node", ToolNode([search_tool]))
    graph.add_node("finalize_node", finalize_node)
    graph.add_edge(START, "plan_node")
    graph.add_edge("plan_node", "search_call_node")
    graph.add_edge("search_call_node", "tool_node")
    graph.add_edge("tool_node", "finalize_node")
    graph.add_edge("finalize_node", END)
    return graph.compile(checkpointer=checkpointer)
