"""最终回复节点。"""

import json

from langchain_core.messages import AIMessage, ToolMessage

from agent.state import AgentState


async def result_node(state: AgentState) -> dict[str, list[AIMessage]]:
    """把已校验工具结果转换为用户可见文本，不暴露内部异常。"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    summary = "目标已经整理完成"
    if isinstance(last_message, ToolMessage):
        try:
            payload = json.loads(str(last_message.content))
            summary = str(payload["data"]["summary"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return {
        "messages": [AIMessage(content=f"{summary}。你现在可以继续添加业务节点和工具。")]
    }
