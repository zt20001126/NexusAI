"""示例智能体使用的无外部依赖工具。"""

import json
from typing import Annotated

from langchain_core.tools import tool
from pydantic import Field

from agent_core.contracts.tools import ToolResult


@tool("ask_user_question")
def ask_user_question() -> str:
    """当缺少明确业务目标时，向用户发起一组结构化问题。"""
    result = ToolResult(
        success=True,
        data={
            "questions": [
                {
                    "id": "goal",
                    "title": "业务目标",
                    "prompt": "你希望这个智能体完成什么具体业务目标？",
                    "allow_custom_input": True,
                }
            ]
        },
        message="等待用户回答",
    )
    return result.model_dump_json()


@tool("summarize_goal")
def summarize_goal(
    goal: Annotated[str, Field(min_length=1, max_length=2_000)],
) -> str:
    """将用户确认的业务目标整理为可继续开发的简短摘要。"""
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


EXAMPLE_TOOLS = [ask_user_question, summarize_goal]
