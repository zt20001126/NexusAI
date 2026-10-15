"""人机协作问题协议。"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.constants import (
    MAX_QUESTION_ANSWER_CHARS,
    MAX_QUESTION_OPTIONS,
    MAX_QUESTION_OPTION_CHARS,
    MAX_QUESTION_SELECTION_CHARS,
    MAX_QUESTIONS_PER_BATCH,
    MAX_QUESTION_SELECTION_COUNT,
)


class Question(BaseModel):
    """一个可由前端稳定渲染和提交的问题。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="稳定且唯一的 snake_case 问题标识",
    )
    title: str = Field(min_length=1, max_length=100, description="简短的问题标题")
    prompt: str = Field(min_length=1, max_length=500, description="清晰、单一的提问内容")
    allow_custom_input: bool = Field(
        default=False,
        description="单选题或多选题是否提供其他自定义输入",
    )
    type: Literal["TextQuestion", "SingleChoice", "MultiChoice", "Confirmation"] = Field(
        default="TextQuestion",
        description="前端支持的结构化问题类型",
    )
    options: list[
        Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_OPTION_CHARS)]
    ] = Field(
        default_factory=list,
        max_length=MAX_QUESTION_OPTIONS,
        description="单选题或多选题的可选项",
    )
    placeholder: str | None = Field(default=None, max_length=200, description="文本输入提示")

    @field_validator("title", "prompt")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        """去除字段两端空白，拒绝空内容和多行排版。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("问题标题和题干不能为空")
        if "\n" in normalized or "\r" in normalized:
            raise ValueError("问题标题和题干必须使用单行纯文本")
        return normalized

    @field_validator("options")
    @classmethod
    def normalize_options(cls, options: list[str]) -> list[str]:
        """统一选项空白并拒绝空项和重复项。"""
        normalized = [option.strip() for option in options]
        if any(not option for option in normalized):
            raise ValueError("问题选项不能为空")
        if any("\n" in option or "\r" in option for option in normalized):
            raise ValueError("每个问题选项必须使用单行纯文本")
        if len({option.casefold() for option in normalized}) != len(normalized):
            raise ValueError("问题选项不能重复")
        return normalized

    @model_validator(mode="after")
    def validate_type_fields(self) -> "Question":
        """确保题型只携带与其匹配的字段和选项。"""
        if self.type in {"SingleChoice", "MultiChoice"}:
            if len(self.options) < 2:
                raise ValueError("单选题和多选题至少需要 2 个选项")
            return self
        if self.options:
            raise ValueError("文本题和确认题不能携带自定义选项")
        if self.allow_custom_input:
            raise ValueError("只有单选题和多选题支持自定义输入")
        return self


class QuestionPayload(BaseModel):
    """追问工具的结构化载荷。"""

    model_config = ConfigDict(extra="forbid")

    questions: list[Question] = Field(
        min_length=1,
        max_length=MAX_QUESTIONS_PER_BATCH,
        description=f"当前批次的问题，最多 {MAX_QUESTIONS_PER_BATCH} 题",
    )

    @model_validator(mode="after")
    def validate_unique_question_ids(self) -> "QuestionPayload":
        """拒绝同一批次中重复的问题标识。"""
        question_ids = [question.id for question in self.questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("同一批次的问题标识不能重复")
        return self

    def validate_answers(self, answers: dict[str, Any]) -> None:
        """校验恢复答案是否符合当前批次的题型和选项。"""
        expected_ids = {question.id for question in self.questions}
        if set(answers) != expected_ids:
            raise ValueError("答案必须与当前问题批次完全匹配")

        for question in self.questions:
            answer = answers[question.id]
            if question.type == "TextQuestion":
                if (
                    not isinstance(answer, str)
                    or not answer.strip()
                    or len(answer) > MAX_QUESTION_ANSWER_CHARS
                ):
                    raise ValueError("文本题必须提供非空文本答案")
                continue

            if question.type == "SingleChoice":
                if (
                    not isinstance(answer, str)
                    or not answer.strip()
                    or len(answer) > MAX_QUESTION_ANSWER_CHARS
                ):
                    raise ValueError("单选题必须选择一个选项")
                if answer not in question.options and not question.allow_custom_input:
                    raise ValueError("单选题答案不在可选项中")
                continue

            if question.type == "MultiChoice":
                if (
                    not isinstance(answer, list)
                    or not answer
                    or len(answer) > MAX_QUESTION_SELECTION_COUNT
                    or any(
                        not isinstance(item, str)
                        or not item.strip()
                        or len(item) > MAX_QUESTION_SELECTION_CHARS
                        for item in answer
                    )
                    or len(answer) != len(set(answer))
                ):
                    raise ValueError("多选题必须提交有效且不重复的选项")
                if not question.allow_custom_input and any(
                    item not in question.options for item in answer
                ):
                    raise ValueError("多选题答案包含不在可选项中的内容")
                continue

            if question.type == "Confirmation" and (
                not isinstance(answer, str) or answer not in ("确认", "取消")
            ):
                raise ValueError("确认题答案必须为确认或取消")
