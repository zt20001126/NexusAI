"""HTTP 请求与响应 DTO，和图状态、数据库模型保持分离。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

AnswerValue = str | int | float | bool | None | list[str]


class ChatRequest(BaseModel):
    """新建或继续一次智能体对话。"""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        min_length=1,
        max_length=20_000,
        description="本轮提交给智能体的用户消息",
    )
    conversation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="可选的会话标识；为空时由 Agent runtime 创建",
    )


class ResumeRequest(BaseModel):
    """向等待中的运行提交结构化答案。"""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(
        min_length=1,
        max_length=128,
        description="待恢复运行所属的会话标识",
    )
    answers: dict[str, AnswerValue] = Field(
        min_length=1,
        max_length=20,
        description="按问题标识提交的结构化答案",
    )

    @field_validator("answers")
    @classmethod
    def validate_answer_bounds(
        cls,
        answers: dict[str, AnswerValue],
    ) -> dict[str, AnswerValue]:
        """限制答案键、文本和列表大小，避免无界内容进入 Checkpoint。"""
        for question_id, value in answers.items():
            if not question_id or len(question_id) > 64:
                raise ValueError("问题标识长度不合法")
            if isinstance(value, str) and len(value) > 2_000:
                raise ValueError("单个答案文本不能超过 2000 个字符")
            if isinstance(value, list):
                if len(value) > 20 or any(len(item) > 500 for item in value):
                    raise ValueError("多选答案超出允许范围")
        return answers
