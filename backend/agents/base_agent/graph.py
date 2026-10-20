"""独立构建并编译输入处理、模型决策、工具执行和输出节点组成的智能体图。"""

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.base_agent.config import BaseAgentConfig
from agents.base_agent.errors import BaseAgentExecutionError
from agents.base_agent.nodes.agent_node import create_agent_node
from agents.base_agent.nodes.input_node import create_input_node
from agents.base_agent.nodes.output_node import output_node
from agents.base_agent.nodes.tool_node import create_tool_node
from agents.base_agent.state import BaseAgentState
from agents.base_agent.tools.registry import ToolRegistry


def _route_after_agent(
    state: BaseAgentState,
    *,
    registered_tool_names: frozenset[str],
) -> Literal["tool_node", "output_node"]:
    """模型请求已注册工具时进入工具节点，否则进入回答节点。"""

    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    tool_calls = getattr(last_message, "tool_calls", [])
    if not tool_calls:
        return "output_node"
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
    return "tool_node"


def build_agent_graph(
    *,
    config: BaseAgentConfig,
    chat_model: BaseChatModel,
    tool_registry: ToolRegistry,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """从显式依赖创建并编译基座图，不依赖任何业务智能体实现。"""

    graph = StateGraph(BaseAgentState)
    graph.add_node("input_node", create_input_node(config))
    graph.add_node(
        "agent_node",
        create_agent_node(
            config=config,
            chat_model=chat_model,
            tool_registry=tool_registry,
        ),
    )
    graph.add_node("tool_node", create_tool_node(tool_registry))
    graph.add_node("output_node", output_node)

    graph.add_edge(START, "input_node")
    graph.add_edge("input_node", "agent_node")
    graph.add_conditional_edges(
        "agent_node",
        lambda state: _route_after_agent(
            state,
            registered_tool_names=tool_registry.names,
        ),
        {
            "tool_node": "tool_node",
            "output_node": "output_node",
        },
    )
    graph.add_edge("tool_node", "agent_node")
    graph.add_edge("output_node", END)
    return graph.compile(checkpointer=checkpointer)
