"""可替换的示例业务工具。"""

import json
from typing import Annotated

from langchain_core.tools import tool
from pydantic import Field

from agent.schemas.tool_result import ToolResult


@tool("summarize_goal")
def summarize_goal(
    goal: Annotated[str, Field(min_length=1, max_length=2_000)],
) -> str:
    """将确认后的业务目标整理成后续节点可消费的结构化结果。"""
    normalized_goal = goal.strip()
    result = ToolResult(
        success=True,
        data={
            "goal": normalized_goal,
            "summary": f"已确认目标：{normalized_goal}",
            "character_count": len(normalized_goal),
        },
        message="目标已整理",
    )
    return json.dumps(result.model_dump(), ensure_ascii=False)
