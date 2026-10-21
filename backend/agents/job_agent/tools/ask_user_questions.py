"""求职助手的结构化单选提问工具。"""

from typing import Literal

from langchain_core.tools import tool
from pydantic import Field

from agent.constants import ASK_USER_QUESTIONS_TOOL_NAME, MAX_QUESTIONS_PER_BATCH
from agent.schemas.question import Question, QuestionPayload
from agent.schemas.tool_result import ToolResult


class JobAgentQuestion(Question):
    """沿用共享题目结构，并将求职助手题型限制为单选。"""

    type: Literal["SingleChoice"] = Field(
        description="求职助手只允许单选题。",
    )


class JobAgentQuestionPayload(QuestionPayload):
    """求职助手提问工具的参数，要求每批提供 1–3 道单选题。"""

    questions: list[JobAgentQuestion] = Field(
        min_length=1,
        max_length=MAX_QUESTIONS_PER_BATCH,
        description=f"当前批次需包含 1–{MAX_QUESTIONS_PER_BATCH} 道单选题。",
    )


@tool(ASK_USER_QUESTIONS_TOOL_NAME, args_schema=JobAgentQuestionPayload)
def ask_user_questions(questions: list[JobAgentQuestion]) -> str:
    """通过结构化题卡收集会影响当前任务的关键选择。

    仅在用户明确要求题卡，或缺少会实质改变结果的关键选择时调用；
    每次调用提交 1–3 道单选题，每题恰好提供 4 个清晰、互斥的选项及说明。
    若需要用户自由描述或无法合理列出 4 个选项，应使用自然语言澄清。
    """

    payload = JobAgentQuestionPayload(questions=questions)
    return ToolResult(
        success=True,
        data=payload.model_dump(mode="json"),
    ).model_dump_json()
