"""构建复用 NexusAI 会话运行时的劳动法律 RAG 图。"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from agent.state import AgentState
from agents.labor_law_agent.nodes.answer import create_legal_answer_node
from agents.labor_law_agent.retrieval import LegalRetrievalService


def build_labor_law_agent_graph(
    checkpointer: Any,
    chat_model: BaseChatModel,
    retrieval_service: LegalRetrievalService,
    max_context_chars: int,
) -> Any:
    """构建单节点 RAG 工作流并复用共享 PostgreSQL Checkpointer。"""
    graph = StateGraph(AgentState)
    graph.add_node(
        "result",
        create_legal_answer_node(chat_model, retrieval_service, max_context_chars),
    )
    graph.add_edge(START, "result")
    graph.add_edge("result", END)
    return graph.compile(checkpointer=checkpointer)

