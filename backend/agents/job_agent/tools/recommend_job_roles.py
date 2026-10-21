"""校验模型自主生成的岗位方向建议。"""

from typing import Any

from langchain_core.tools import tool

from agent.schemas.tool_result import ToolResult
from agents.job_agent.recommendation.schemas import RecommendationRequest
from agents.job_agent.recommendation.service import validate_recommendations


@tool("recommend_job_roles", args_schema=RecommendationRequest)
def recommend_job_roles(
    profile: dict[str, Any],
    roles: list[dict[str, Any]] | None = None,
) -> str:
    """提交模型生成的岗位方向与理由，校验资料充分性及每项依据。"""

    request = RecommendationRequest.model_validate({"profile": profile, "roles": roles or []})
    result = validate_recommendations(request)
    return ToolResult(
        success=True,
        data=result.model_dump(mode="json"),
    ).model_dump_json()
