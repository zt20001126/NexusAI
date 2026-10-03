"""结构化人机协作工具。"""

from langchain_core.tools import tool

from agent.schemas.question import Question, QuestionPayload
from agent.schemas.tool_result import ToolResult


@tool("ask_user_question")
def ask_user_question() -> str:
    """当缺少明确业务目标时，向用户发起一组结构化问题。"""
    payload = QuestionPayload(
        questions=[
            Question(
                id="goal",
                title="业务目标",
                prompt="你希望这个智能体完成什么具体业务目标？",
            )
        ]
    )
    return ToolResult(
        success=True,
        data=payload.model_dump(),
        message="等待用户回答",
    ).model_dump_json()
