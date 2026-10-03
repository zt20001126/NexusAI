"""人机协作问题协议。"""

from pydantic import BaseModel, ConfigDict, Field


class Question(BaseModel):
    """一个可由前端稳定渲染和提交的问题。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=500)
    allow_custom_input: bool = True


class QuestionPayload(BaseModel):
    """追问工具的结构化载荷。"""

    questions: list[Question] = Field(min_length=1, max_length=20)
