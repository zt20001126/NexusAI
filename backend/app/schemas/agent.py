"""HTTP 请求与响应 DTO，和图状态、数据库模型保持分离。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.constants import MAX_REFERENCE_IMAGE_COUNT

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
        pattern=r"^[1-9][0-9]{0,18}$",
        description="可选的会话标识；为空时由 Agent runtime 创建",
    )
    attachment_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_REFERENCE_IMAGE_COUNT,
        description="已上传并暂存的参考图片标识，单次最多 3 张",
    )

    @field_validator("attachment_ids")
    @classmethod
    def validate_attachment_ids(cls, values: list[str]) -> list[str]:
        """拒绝空白和重复标识，避免同一图片被意外重复发送。"""
        if any(not value.isdigit() or value.startswith("0") or len(value) > 19 for value in values):
            raise ValueError("附件标识不合法")
        if len(set(values)) != len(values):
            raise ValueError("附件标识不能重复")
        return values


class ResumeRequest(BaseModel):
    """向等待中的运行提交结构化答案。"""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(
        pattern=r"^[1-9][0-9]{0,18}$",
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
            if isinstance(value, str) and not value.strip():
                raise ValueError("必要问题不能提交空白答案")
            if value is None:
                raise ValueError("必要问题不能提交空答案")
            if isinstance(value, list):
                if (
                    not value
                    or len(value) > 20
                    or any(not item.strip() or len(item) > 500 for item in value)
                ):
                    raise ValueError("多选答案超出允许范围")
        return answers
