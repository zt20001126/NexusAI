"""独立构建并编译输入处理、模型决策、工具执行和输出节点组成的智能体图。"""

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.constants import ASK_USER_QUESTIONS_TOOL_NAME
from agents.job_agent.config import JobAgentConfig
from agents.job_agent.errors import JobAgentExecutionError
from agents.job_agent.nodes.agent_node import create_agent_node
from agents.job_agent.nodes.input_node import create_input_node
from agents.job_agent.nodes.output_node import output_node
from agents.job_agent.nodes.resume_optimization_node import (
    STAGE_TOOL,
    create_resume_optimization_node,
)
from agents.job_agent.nodes.tool_node import create_tool_node
from agents.job_agent.state import JobAgentState
from agents.job_agent.tools.registry import ToolRegistry


def _route_after_agent(
    state: JobAgentState,
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
        raise JobAgentExecutionError(
            "只有 AI 消息可以发起工具调用",
            code="invalid_tool_call_message",
        )

    unknown_tool_names = {
        str(tool_call.get("name", ""))
        for tool_call in tool_calls
        if tool_call.get("name") not in registered_tool_names
    }
    if unknown_tool_names:
        raise JobAgentExecutionError(
            "模型请求了未注册的工具",
            code="unregistered_tool_call",
        )
    if any(
        tool_call.get("name") == ASK_USER_QUESTIONS_TOOL_NAME
        for tool_call in tool_calls
    ) and len(tool_calls) != 1:
        raise JobAgentExecutionError(
            "提问工具必须单独调用，每批问题应放在一次工具调用中",
            code="invalid_question_tool_call_batch",
        )
    return "tool_node"


def _route_after_tools(
    state: JobAgentState,
) -> Literal["agent_node", "pause", "resume_optimization_node"]:
    """普通工具回到模型；提问工具结束本阶段并交由 Runner 等待答案。"""

    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if (
        isinstance(last_message, ToolMessage)
        and last_message.name == ASK_USER_QUESTIONS_TOOL_NAME
    ):
        return "pause"
    if isinstance(last_message, ToolMessage) and last_message.name == STAGE_TOOL:
        return "resume_optimization_node"
    return "agent_node"


def build_agent_graph(
    *,
    config: JobAgentConfig,
    chat_model: BaseChatModel,
    tool_registry: ToolRegistry,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    resume_optimization_writer: Any | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """从注入的模型、工具和 Checkpointer 创建求职智能体图。"""

    graph = StateGraph(JobAgentState)
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
    graph.add_node(
        "resume_optimization_node",
        create_resume_optimization_node(resume_optimization_writer),
    )

    graph.add_edge(START, "input_node")
    graph.add_edge("input_node", "resume_optimization_node")
    graph.add_edge("resume_optimization_node", "agent_node")
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
    graph.add_conditional_edges(
        "tool_node",
        _route_after_tools,
        {
            "agent_node": "agent_node",
            "pause": END,
            "resume_optimization_node": "resume_optimization_node",
        },
    )
    graph.add_edge("output_node", END)
    return graph.compile(checkpointer=checkpointer)
