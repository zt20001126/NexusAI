"""商品必要信息判断节点。"""

import json
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agent.constants import MAX_QUESTION_ROUNDS_PER_RUN
from agents.listing_agent.constants import LISTING_VERSION_COUNT
from agents.listing_agent.prompts import PLAN_PROMPT
from agents.listing_agent.schemas import ListingPlan
from agents.listing_agent.state import ListingAgentState
from agents.listing_agent.nodes._shared import _has_answer, _parse_model_json


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

        question_round_count = state.get("question_round_count", 0)
        if (
            not isinstance(question_round_count, int)
            or isinstance(question_round_count, bool)
        ):
            question_round_count = 0
        remaining_question_rounds = max(
            0,
            MAX_QUESTION_ROUNDS_PER_RUN - question_round_count,
        )

        context = {
            "seller_message": state.get("original_request", ""),
            "image_analysis": state.get("image_analysis", {}),
            "confirmed_answers": confirmed_answers,
            "question_progress": {
                "completed_rounds": question_round_count,
                "max_rounds": MAX_QUESTION_ROUNDS_PER_RUN,
                "remaining_rounds": remaining_question_rounds,
            },
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
        unanswered_questions = (
            [
                question
                for question in plan.questions
                if question.id not in answered_ids
            ]
            if remaining_question_rounds > 0
            else []
        )
        return {
            "confirmed_answers": confirmed_answers,
            "product_facts": plan.product_facts,
            "questions": [
                question.model_dump(mode="json") for question in unanswered_questions
            ],
        }

    return plan_node
