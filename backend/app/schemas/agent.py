"""HTTP 请求与响应 DTO，和图状态、数据库模型保持分离。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.constants import (
    MAX_QUESTION_OPTION_CHARS,
    MAX_QUESTION_SELECTION_COUNT,
    MAX_QUESTIONS_PER_BATCH,
    MAX_REFERENCE_IMAGE_COUNT,
)

AnswerValue = str | list[str]


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
    request_id: str | None = Field(
        default=None,
        min_length=16,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="本次提交的幂等请求标识；客户端重试时必须复用",
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
        max_length=MAX_QUESTIONS_PER_BATCH,
        description="按问题标识提交的结构化答案",
    )
    request_id: str | None = Field(
        default=None,
        min_length=16,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="追问恢复请求的幂等标识；重试时复用",
    )
    after_event_id: str | None = Field(
        default=None,
        pattern=r"^[0-9]+-[0-9]+$",
        description="提交答案前已收到的事件游标",
    )

    @field_validator("answers")
    @classmethod
    def validate_answer_bounds(
        cls,
        answers: dict[str, AnswerValue],
    ) -> dict[str, AnswerValue]:
        """限制答案键、选项标签和多选数量，避免无界内容进入 Checkpoint。"""
        for question_id, value in answers.items():
            if not question_id or len(question_id) > 64:
                raise ValueError("问题标识长度不合法")
            if isinstance(value, str) and not value.strip():
                raise ValueError("选择题答案不能是空白内容")
            if isinstance(value, str) and len(value) > MAX_QUESTION_OPTION_CHARS:
                raise ValueError("选择题答案长度超出选项标签限制")
            if isinstance(value, list):
                if (
                    not value
                    or len(value) > MAX_QUESTION_SELECTION_COUNT
                    or any(
                        not item.strip() or len(item) > MAX_QUESTION_OPTION_CHARS
                        for item in value
                    )
                    or len(value) != len(set(value))
                ):
                    raise ValueError("多选答案为空、重复或超出允许范围")
        return answers


class ActiveAgentRunItem(BaseModel):
    """当前主体的一条活动 Agent 运行恢复信息。"""

    conversation_id: str = Field(description="活动会话 ID")
    run_id: str = Field(description="当前运行 ID")
    agent: str = Field(description="运行所属智能体类型")
    status: str = Field(description="后台运行状态")
    last_event_id: str | None = Field(description="最后一个已持久化事件游标")


class AgentRunStatusResponse(BaseModel):
    """单轮 Agent 执行状态和事件续接游标。"""

    conversation_id: str = Field(description="运行所属会话 ID")
    run_id: str = Field(description="运行 ID")
    status: str = Field(description="后台运行状态")
    last_event_id: str | None = Field(description="最后一个已持久化事件游标")
    error: str | None = Field(description="可安全展示的失败摘要")
