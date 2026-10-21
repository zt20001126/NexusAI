"""求职智能体的调用输入与稳定输出模型。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.enums import AgentType
from agent.schemas.question import QuestionPayload

class AgentRequest(BaseModel):
    """单轮调用的用户输入；会话历史由可选 Checkpointer 管理。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(
        min_length=1,
        description="本轮用户消息，不能是空白文本。",
    )


class AgentResponse(BaseModel):
    """求职智能体返回的稳定结果，可表示最终回答或等待用户选择。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: AgentType = Field(description="生成此回复的智能体类型。")
    status: Literal["completed", "waiting"] = Field(
        description="completed 表示已生成回答；waiting 表示当前需要用户回答题卡。",
    )
    answer: str | None = Field(
        default=None,
        min_length=1,
        description="completed 状态下的最终回复文本。",
    )
    questions: QuestionPayload | None = Field(
        default=None,
        description="waiting 状态下等待用户回答的问题批次。",
    )

    @model_validator(mode="after")
    def validate_response_state(self) -> "AgentResponse":
        """确保回答文本与待答题卡只出现在相应的响应状态中。"""

        if self.status == "completed":
            if self.answer is None or not self.answer.strip() or self.questions is not None:
                raise ValueError("completed 响应必须只包含非空 answer")
            return self
        if self.answer is not None or self.questions is None:
            raise ValueError("waiting 响应必须只包含 questions")
        return self
