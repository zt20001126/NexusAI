"""把服务端检索计划和可信运行上下文交给 OpenAlex 工具。"""

import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage

from agents.research_agent.constants import RESEARCH_DEFAULT_LIMIT, RESEARCH_TOOL_NAME
from agents.research_agent.state import ResearchAgentState


def create_search_call_node(max_search_rounds: int) -> Callable[..., Any]:
    """创建仅携带短计划和服务端标识的工具调用节点。"""

    def search_call_node(state: ResearchAgentState) -> dict[str, Any]:
        """构造 OpenAlex 工具调用；论文内容不会进入工具参数或 Checkpoint。"""
        options = state.get("research_options", {})
        arguments = {
            "plan": state.get("search_plan", {}),
            "limit": options.get("limit", RESEARCH_DEFAULT_LIMIT),
            "original_request": state.get("original_request", ""),
            "task_result_id": state.get("task_result_id", ""),
            "principal_id": state.get("principal_id", ""),
            "conversation_id": state.get("conversation_id", ""),
            "run_id": state.get("run_id", ""),
            "agent_id": state.get("agent_id", ""),
            "max_search_rounds": max_search_rounds,
        }
        call = {
            "name": RESEARCH_TOOL_NAME,
            "args": arguments,
            "id": uuid.uuid4().hex,
            "type": "tool_call",
        }
        return {"messages": [AIMessage(content="", tool_calls=[call])]}

    return search_call_node
