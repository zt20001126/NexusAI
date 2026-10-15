"""Listing 文案生成节点。"""

import json
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.listing_agent.constants import LISTING_SAVE_TOOL_NAME
from agents.listing_agent.prompts import GENERATION_PROMPT
from agents.listing_agent.schemas import ListingResult
from agents.listing_agent.state import ListingAgentState
from agents.listing_agent.nodes._shared import _parse_model_json


def create_generation_node(chat_model: BaseChatModel) -> Callable[..., Any]:
    """创建输出严格遵守 ListingResult Schema 的内容生成节点。"""

    async def generation_node(state: ListingAgentState) -> dict[str, Any]:
        """基于已核实信息生成并校验三个完整版本。"""
        context = {
            "seller_message": state.get("original_request", ""),
            "image_analysis": state.get("image_analysis", {}),
            "product_facts": state.get("product_facts", {}),
            "confirmed_answers": state.get("confirmed_answers", {}),
        }
        response = await chat_model.ainvoke(
            [
                SystemMessage(
                    content=(
                        GENERATION_PROMPT
                        + "\n输出 Schema："
                        + json.dumps(ListingResult.model_json_schema(), ensure_ascii=False)
                    )
                ),
                HumanMessage(content=json.dumps(context, ensure_ascii=False)),
            ]
        )
        listing_result = _parse_model_json(response.content, ListingResult)
        arguments = {
            "task_result_id": state.get("task_result_id", ""),
            "principal_id": state.get("principal_id", ""),
            "conversation_id": state.get("conversation_id", ""),
            "run_id": state.get("run_id", ""),
            "original_request": state.get("original_request", ""),
            "attachment_ids": state.get("attachment_ids", []),
            "confirmed_answers": state.get("confirmed_answers", {}),
            "listing_result": listing_result.model_dump(mode="json"),
        }
        call = {
            "name": LISTING_SAVE_TOOL_NAME,
            "args": arguments,
            "id": uuid.uuid4().hex,
            "type": "tool_call",
        }
        return {
            "listing_result": listing_result.model_dump(mode="json"),
            "messages": [AIMessage(content="", tool_calls=[call])],
        }

    return generation_node
