"""智能体基座的调用输入与稳定输出模型。"""

from pydantic import BaseModel, ConfigDict, Field

from agent.enums import AgentType

class AgentRequest(BaseModel):
    """单轮调用的用户输入；会话历史由可选 Checkpointer 管理。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(
        min_length=1,
        description="本轮用户消息，不能是空白文本。",
    )


class AgentResponse(BaseModel):
    """基座返回给调用方的最小稳定响应，不暴露内部图状态。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: AgentType = Field(description="生成此回复的智能体类型。")
    answer: str = Field(min_length=1, description="智能体最终回复文本。")
