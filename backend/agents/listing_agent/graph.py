"""组装 Listing 智能体的图片识别、追问、生成和结果节点。"""

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from agent.persistence.interfaces import AttachmentStore, TaskResultStore
from agent.tools.registry import PAUSE_TOOL_NAMES
from agents.listing_agent.nodes import (
    create_ask_node,
    create_generation_node,
    create_plan_node,
    create_vision_node,
    result_node,
    route_after_plan,
)
from agents.listing_agent.providers.tokenhub_vision import TokenHubVisionClient
from agents.listing_agent.state import ListingAgentState
from agents.listing_agent.tools.task_result import create_listing_task_result_tools


def route_initial(state: ListingAgentState) -> Literal["vision_node", "plan_node"]:
    """恢复时沿用已保存的视觉结果，避免重复发送图片。"""
    return "plan_node" if state.get("image_analysis") else "vision_node"


def route_after_generation(state: ListingAgentState) -> Literal["tool_node"]:
    """生成节点只产生受控结果保存工具调用。"""
    del state
    return "tool_node"


def route_after_listing_tools(state: ListingAgentState) -> Literal["__end__", "result_node"]:
    """批量追问暂停运行；结果保存后生成结束回复。"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if isinstance(last_message, ToolMessage) and last_message.name in PAUSE_TOOL_NAMES:
        return END
    return "result_node"


def build_listing_agent_graph(
    checkpointer: Any,
    chat_model: BaseChatModel,
    vision_client: TokenHubVisionClient,
    task_result_store: TaskResultStore,
    attachment_store: AttachmentStore,
) -> Any:
    """构建独立 Listing 图并注入模型、附件及任务结果协议。"""
    ask_tool, save_tool = create_listing_task_result_tools(task_result_store)
    graph = StateGraph(ListingAgentState)
    graph.add_node("vision_node", create_vision_node(vision_client, attachment_store))
    graph.add_node("plan_node", create_plan_node(chat_model))
    graph.add_node("ask_node", create_ask_node())
    graph.add_node("generation_node", create_generation_node(chat_model))
    graph.add_node("tool_node", ToolNode([ask_tool, save_tool]))
    graph.add_node("result_node", result_node)
    graph.add_conditional_edges(START, route_initial)
    graph.add_edge("vision_node", "plan_node")
    graph.add_conditional_edges("plan_node", route_after_plan)
    graph.add_edge("ask_node", "tool_node")
    graph.add_conditional_edges("generation_node", route_after_generation)
    graph.add_conditional_edges("tool_node", route_after_listing_tools)
    graph.add_edge("result_node", END)
    compiled = graph.compile(checkpointer=checkpointer)
    compiled.pause_tool_names = PAUSE_TOOL_NAMES
    return compiled
