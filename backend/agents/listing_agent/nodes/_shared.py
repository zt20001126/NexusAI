"""Listing 节点共用的输入验证辅助函数。"""

from typing import Any

from pydantic import ValidationError

from agents.listing_agent.schemas import ListingImageAnalysis, ListingPlan, ListingResult


def _has_answer(value: Any) -> bool:
    """空白文本和空列表不构成必要问题的回答。"""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(_has_answer(item) for item in value)
    return value is not None


def _parse_model_json(
    content: Any,
    schema: type[ListingImageAnalysis] | type[ListingPlan] | type[ListingResult],
) -> ListingImageAnalysis | ListingPlan | ListingResult:
    """验证模型 JSON；不修复或猜测缺失字段。"""
    if not isinstance(content, str):
        raise ValueError("模型响应必须为 JSON 文本")
    try:
        return schema.model_validate_json(content.strip())
    except ValidationError:
        raise ValueError("模型返回的 JSON 未通过 Listing Schema 校验") from None
