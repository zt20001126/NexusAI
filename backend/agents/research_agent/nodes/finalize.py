"""根据任务结果摘要确定性生成助手回复。"""

from langchain_core.messages import AIMessage, ToolMessage

from agent.schemas.tool_result import ToolResult
from agents.research_agent.constants import RESEARCH_TOOL_NAME
from agents.research_agent.state import ResearchAgentState


def finalize_node(state: ResearchAgentState) -> dict[str, list[AIMessage]]:
    """只使用工具返回的状态和数量生成结尾，不复述论文事实。"""
    tool_message = next(
        (
            message
            for message in reversed(state.get("messages", []))
            if isinstance(message, ToolMessage) and message.name == RESEARCH_TOOL_NAME
        ),
        None,
    )
    if tool_message is None:
        return {"messages": [AIMessage(content="科研文献检索未能完成，请稍后重试。")]}
    try:
        result = ToolResult.model_validate_json(str(tool_message.content))
    except ValueError:
        return {"messages": [AIMessage(content="科研文献检索结果无法识别，请稍后重试。")]}
    data = result.data
    status = data.get("status")
    message = data.get("message")
    if isinstance(message, str) and status in {"success", "partial", "no_results", "failed"}:
        return {"messages": [AIMessage(content=message)]}
    return {"messages": [AIMessage(content="科研文献检索未能完成，请稍后重试。")]}
