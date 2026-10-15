"""组装淘宝图片智能体的验证、对话、追问和工具节点。"""

from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from agent.tools.registry import PAUSE_TOOL_NAMES
from agents.image_generation.nodes.ask_node import ask_node
from agents.image_generation.nodes.chat_node import create_chat_node
from agents.image_generation.nodes.result_node import result_node
from agents.image_generation.nodes.validation_node import validation_node
from agents.image_generation.state import ImageAgentState
from agents.image_generation.tools.ask_parameters import create_ask_image_parameters_tool
from agents.image_generation.tools.generate_image import create_generate_image_tool
from agents.image_generation.providers.result_downloader import ImageResultDownloader
from agents.image_generation.providers.tokenhub_client import TokenHubImageClient
from agent.persistence.interfaces import AttachmentStore, TaskResultStore
from infra.settings import AppSettings


def route_after_chat(state: ImageAgentState) -> Literal["ask_node", "__end__"]:
    """只有明确生图意图继续检查参数。"""
    return "ask_node" if state.get("is_image_generation") else END


def route_after_ask(state: ImageAgentState) -> Literal["tool_node", "__end__"]:
    """根据追问节点产生的受控工具调用决定执行或等待。"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    return "tool_node" if getattr(last_message, "tool_calls", None) else END


def route_after_tools(state: ImageAgentState) -> Literal["result_node", "__end__"]:
    """结构化追问结束本轮；图片生成结果进入结果回复节点。"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if isinstance(last_message, ToolMessage) and last_message.name in PAUSE_TOOL_NAMES:
        return END
    return "result_node"


def build_image_agent_graph(
    checkpointer: Any,
    chat_model: BaseChatModel,
    settings: AppSettings,
    image_client: TokenHubImageClient,
    downloader: ImageResultDownloader,
    task_result_store: TaskResultStore,
    attachment_store: AttachmentStore,
) -> Any:
    """构建独立图片图，复用共享问题协议和 Checkpoint。"""
    ask_tool = create_ask_image_parameters_tool(task_result_store)
    generate_tool = create_generate_image_tool(
        settings,
        image_client,
        downloader,
        task_result_store,
        attachment_store,
    )
    graph = StateGraph(ImageAgentState)
    graph.add_node("validation_node", validation_node)
    graph.add_node("chat_node", create_chat_node(chat_model))
    graph.add_node("ask_node", ask_node)
    graph.add_node("tool_node", ToolNode([ask_tool, generate_tool]))
    graph.add_node("result_node", result_node)
    graph.add_edge(START, "validation_node")
    graph.add_edge("validation_node", "chat_node")
    graph.add_conditional_edges("chat_node", route_after_chat)
    graph.add_conditional_edges("ask_node", route_after_ask)
    graph.add_conditional_edges("tool_node", route_after_tools)
    graph.add_edge("result_node", END)
    compiled = graph.compile(checkpointer=checkpointer)
    compiled.pause_tool_names = PAUSE_TOOL_NAMES
    return compiled
