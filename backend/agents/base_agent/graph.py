"""独立构建并编译校验、对话、工具和回答节点组成的智能体图。"""

from enum import StrEnum
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.base_agent.config import BaseAgentConfig
from agents.base_agent.errors import BaseAgentExecutionError
from agents.base_agent.nodes.answer_node import answer_node
from agents.base_agent.nodes.chat_node import create_chat_node
from agents.base_agent.nodes.tool_node import create_tool_node
from agents.base_agent.nodes.validation_node import create_validation_node
from agents.base_agent.state import BaseAgentState
from agents.base_agent.tools.registry import ToolRegistry


class NodeName(StrEnum):
    """基座图中稳定、可检索的节点标识。"""

    VALIDATION = "validation_node"
    CHAT = "chat_node"
    TOOL = "tool_node"
    ANSWER = "answer_node"


def _route_after_chat(
    state: BaseAgentState,
    *,
    registered_tool_names: frozenset[str],
) -> NodeName:
    """模型请求已注册工具时进入工具节点，否则进入回答节点。"""

    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    tool_calls = getattr(last_message, "tool_calls", [])
    if not tool_calls:
        return NodeName.ANSWER
    if not isinstance(last_message, AIMessage):
        raise BaseAgentExecutionError(
            "只有 AI 消息可以发起工具调用",
            code="invalid_tool_call_message",
        )

    unknown_tool_names = {
        str(tool_call.get("name", ""))
        for tool_call in tool_calls
        if tool_call.get("name") not in registered_tool_names
    }
    if unknown_tool_names:
        raise BaseAgentExecutionError(
            "模型请求了未注册的工具",
            code="unregistered_tool_call",
        )
    return NodeName.TOOL


def build_agent_graph(
    *,
    config: BaseAgentConfig,
    chat_model: BaseChatModel,
    tool_registry: ToolRegistry,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """从显式依赖创建并编译基座图，不依赖任何业务智能体实现。"""

    graph = StateGraph(BaseAgentState)
    graph.add_node(NodeName.VALIDATION, create_validation_node(config))
    graph.add_node(
        NodeName.CHAT,
        create_chat_node(
            config=config,
            chat_model=chat_model,
            tool_registry=tool_registry,
        ),
    )
    graph.add_node(NodeName.TOOL, create_tool_node(tool_registry))
    graph.add_node(NodeName.ANSWER, answer_node)

    graph.add_edge(START, NodeName.VALIDATION)
    graph.add_edge(NodeName.VALIDATION, NodeName.CHAT)
    graph.add_conditional_edges(
        NodeName.CHAT,
        lambda state: _route_after_chat(
            state,
            registered_tool_names=tool_registry.names,
        ),
        {
            NodeName.TOOL: NodeName.TOOL,
            NodeName.ANSWER: NodeName.ANSWER,
        },
    )
    graph.add_edge(NodeName.TOOL, NodeName.CHAT)
    graph.add_edge(NodeName.ANSWER, END)
    return graph.compile(checkpointer=checkpointer)
