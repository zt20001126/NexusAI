"""Listing 图片分析、问题判断、文案生成及工具路由节点。"""

import asyncio
import json
import uuid
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from agent.persistence.interfaces import AttachmentStore
from agent.schemas.tool_result import ToolResult
from agents.listing_agent.constants import (
    LISTING_ASK_TOOL_NAME,
    LISTING_SAVE_TOOL_NAME,
    LISTING_VERSION_COUNT,
)
from agents.listing_agent.prompts import GENERATION_PROMPT, PLAN_PROMPT
from agents.listing_agent.providers.tokenhub_vision import TokenHubVisionClient
from agents.listing_agent.schemas import ListingPlan, ListingResult
from agents.listing_agent.state import ListingAgentState


def create_vision_node(
    vision_client: TokenHubVisionClient,
    attachment_store: AttachmentStore,
) -> Callable[..., Any]:
    """创建通过授权附件读取商品图片的异步分析节点。"""

    async def vision_node(state: ListingAgentState) -> dict[str, Any]:
        """读取已绑定图片并提取外观、包装文字和可见特征。"""
        attachment_ids = state.get("attachment_ids", [])
        if not attachment_ids:
            raise ValueError("Listing 生成需要至少一张商品图片")
        attachments = await asyncio.to_thread(
            attachment_store.list_for_generation,
            attachment_ids,
            state.get("principal_id", ""),
            state.get("conversation_id", ""),
        )
        reference_images = [
            (attachment.mime_type, attachment.image_data) for attachment in attachments
        ]
        analysis = await vision_client.analyze(reference_images)
        return {"image_analysis": analysis.model_dump(mode="json")}

    return vision_node


def create_plan_node(chat_model: BaseChatModel) -> Callable[..., Any]:
    """创建基于图片观察和商家回答的必要信息判断节点。"""

    async def plan_node(state: ListingAgentState) -> dict[str, Any]:
        """一次判断全部当前缺口，并合并本轮结构化答案。"""
        confirmed_answers = dict(state.get("confirmed_answers", {}))
        submitted_answers = state.get("resume_answers", {})
        for question_id, value in submitted_answers.items():
            if not _has_answer(value):
                raise ValueError("必要问题必须提供非空答案")
            confirmed_answers[question_id] = value

        context = {
            "seller_message": state.get("original_request", ""),
            "image_analysis": state.get("image_analysis", {}),
            "confirmed_answers": confirmed_answers,
            "required_output": {
                "title": True,
                "selling_points": True,
                "plain_text_description": True,
                "keywords": True,
                "product_attributes": True,
                "version_count": LISTING_VERSION_COUNT,
            },
        }
        response = await chat_model.ainvoke(
            [
                SystemMessage(
                    content=(
                        PLAN_PROMPT
                        + "\n输出 Schema："
                        + json.dumps(ListingPlan.model_json_schema(), ensure_ascii=False)
                    )
                ),
                HumanMessage(content=json.dumps(context, ensure_ascii=False)),
            ]
        )
        plan = _parse_model_json(response.content, ListingPlan)
        answered_ids = set(confirmed_answers)
        unanswered_questions = [
            question for question in plan.questions if question.id not in answered_ids
        ]
        return {
            "confirmed_answers": confirmed_answers,
            "product_facts": plan.product_facts,
            "questions": [question.model_dump(mode="json") for question in unanswered_questions],
        }

    return plan_node


def route_after_plan(state: ListingAgentState) -> Literal["ask_node", "generation_node"]:
    """有必要核实的信息时先追问；否则进入生成。"""
    return "ask_node" if state.get("questions") else "generation_node"


def create_ask_node() -> Callable[..., dict[str, list[AIMessage]]]:
    """创建由服务端补全可信身份的批量追问工具调用节点。"""

    def ask_node(state: ListingAgentState) -> dict[str, list[AIMessage]]:
        """一次提交当前全部问题，并保留商品识别及事实快照。"""
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
        return {"messages": [AIMessage(content="", tool_calls=[call])]}

    return ask_node


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


def _parse_model_json(content: Any, schema: type[ListingPlan] | type[ListingResult]):
    """验证模型 JSON；不修复或猜测缺失字段。"""
    if not isinstance(content, str):
        raise ValueError("模型响应必须为 JSON 文本")
    try:
        return schema.model_validate_json(content.strip())
    except ValidationError:
        raise ValueError("模型返回的 JSON 未通过 Listing Schema 校验") from None


def _has_answer(value: Any) -> bool:
    """空白文本和空列表不构成必要问题的回答。"""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(_has_answer(item) for item in value)
    return value is not None
