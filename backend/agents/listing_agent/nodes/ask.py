"""补充信息批量追问节点。"""

import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage

from agents.listing_agent.constants import LISTING_ASK_TOOL_NAME
from agents.listing_agent.state import ListingAgentState


def create_ask_node() -> Callable[..., dict[str, Any]]:
    """创建由服务端补全可信身份的批量追问工具调用节点。"""

    def ask_node(state: ListingAgentState) -> dict[str, list[AIMessage]]:
        """提交当前批次的问题，并保留商品识别及事实快照。"""
        arguments = {
            "questions": state.get("questions", []),
            "task_result_id": state.get("task_result_id", ""),
            "principal_id": state.get("principal_id", ""),
            "conversation_id": state.get("conversation_id", ""),
            "run_id": state.get("run_id", ""),
            "original_request": state.get("original_request", ""),
            "attachment_ids": state.get("attachment_ids", []),
            "image_analysis": state.get("image_analysis", {}),
            "product_facts": state.get("product_facts", {}),
            "confirmed_answers": state.get("confirmed_answers", {}),
        }
        call = {
            "name": LISTING_ASK_TOOL_NAME,
            "args": arguments,
            "id": uuid.uuid4().hex,
            "type": "tool_call",
        }
        return {
            "question_round_count": state.get("question_round_count", 0) + 1,
            "messages": [AIMessage(content="", tool_calls=[call])],
        }

    return ask_node
