"""将用户请求解析为经校验的 OpenAlex 检索计划。"""

import json
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agents.research_agent.constants import RESEARCH_MAX_QUERY_CHARS
from agents.research_agent.prompts import RESEARCH_PLAN_PROMPT
from agents.research_agent.schemas import ResearchSearchPlan
from agents.research_agent.state import ResearchAgentState

logger = logging.getLogger(__name__)
PLAN_OVERRIDE_FIELDS = ("year_from", "year_to", "language", "sort")


def create_plan_node(chat_model: BaseChatModel) -> Callable[..., Any]:
    """创建只解析检索词与过滤条件的计划节点。"""

    async def plan_node(state: ResearchAgentState) -> dict[str, Any]:
        """用模型提取计划；模型不可用时回退到用户原始主题词。"""
        original_request = state.get("original_request", "").strip()
        options = state.get("research_options", {})
        context = {
            "user_request": original_request,
            "requested_limit": options.get("limit"),
            "explicit_constraints": {
                key: options.get(key)
                for key in PLAN_OVERRIDE_FIELDS
                if options.get(key) is not None
            },
        }
        try:
            response = await chat_model.ainvoke(
                [
                    SystemMessage(
                        content=(
                            RESEARCH_PLAN_PROMPT
                            + "\n输出 Schema："
                            + json.dumps(ResearchSearchPlan.model_json_schema(), ensure_ascii=False)
                        )
                    ),
                    HumanMessage(content=json.dumps(context, ensure_ascii=False)),
                ]
            )
            if not isinstance(response.content, str):
                raise ValueError("检索计划必须为 JSON 文本")
            plan = ResearchSearchPlan.model_validate_json(response.content.strip())
        except Exception:
            logger.warning("科研检索计划解析失败，使用用户原始查询词")
            plan = ResearchSearchPlan(
                query=original_request[:RESEARCH_MAX_QUERY_CHARS],
            )

        plan_values = plan.model_dump(mode="python")
        for field_name in PLAN_OVERRIDE_FIELDS:
            if options.get(field_name) is not None:
                plan_values[field_name] = options[field_name]
        validated_plan = ResearchSearchPlan.model_validate(plan_values)
        return {"search_plan": validated_plan.model_dump(mode="json")}

    return plan_node
