"""Listing 结果保存后的助手回复节点。"""

from langchain_core.messages import AIMessage, ToolMessage

from agent.schemas.tool_result import ToolResult
from agents.listing_agent.constants import (
    LISTING_SAVE_TOOL_NAME,
    LISTING_VERSION_COUNT,
)
from agents.listing_agent.state import ListingAgentState


def result_node(state: ListingAgentState) -> dict[str, list[AIMessage]]:
    """将结果保存状态转换成简短助手回复，完整 JSON 由结果卡片读取。"""
    messages = state.get("messages", [])
    tool_message = next(
        (
            message
            for message in reversed(messages)
            if isinstance(message, ToolMessage) and message.name == LISTING_SAVE_TOOL_NAME
        ),
        None,
    )
    if tool_message is None:
        return {"messages": [AIMessage(content="Listing 结果未能保存，请稍后重试。")]}
    try:
        payload = ToolResult.model_validate_json(str(tool_message.content))
    except ValueError:
        return {"messages": [AIMessage(content="Listing 结果无法识别，请稍后重试。")]}
    content = (
        f"已完成 {LISTING_VERSION_COUNT} 个淘宝 Listing 版本，结果已保存。"
        if payload.success
        else payload.message
    )
    return {"messages": [AIMessage(content=content[:2_000])]}
