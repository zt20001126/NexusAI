"""把生图工具结果转换成稳定的助手回复。"""

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from agent.schemas.tool_result import ToolResult
from agents.image_agent.state import ImageAgentState


def result_node(state: ImageAgentState) -> dict[str, list[AIMessage]]:
    """读取生成工具的结构化结果并输出可安全展示的简短消息。

    输入：ToolNode 产生的 generate_image ToolMessage。
    输出：助手最终回复；图片卡片通过 task_result.updated 事件单独呈现。
    下一节点：END。
    """
    messages = state.get("messages", [])
    tool_message = next(
        (
            message
            for message in reversed(messages)
            if isinstance(message, ToolMessage) and message.name == "generate_image"
        ),
        None,
    )
    if tool_message is None:
        return {"messages": [AIMessage(content="图片生成没有返回结果，请稍后重试。")]}
    try:
        payload = ToolResult.model_validate_json(str(tool_message.content))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"messages": [AIMessage(content="图片生成结果无法识别，请稍后重试。")]}

    summary: Any = payload.data.get("summary")
    if payload.success:
        content = "图片已生成并保存到本次会话。"
    elif isinstance(summary, str) and summary:
        content = summary
    else:
        content = payload.message
    return {"messages": [AIMessage(content=content[:2_000])]}
