"""所有智能体共用的人机协作问题协议。"""

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.constants import (
    MAX_QUESTION_OPTION_CHARS,
    MAX_QUESTION_OPTION_DESCRIPTION_CHARS,
    MAX_QUESTIONS_PER_BATCH,
    MAX_QUESTION_SELECTION_COUNT,
    QUESTION_OPTION_COUNT,
)


class QuestionOption(BaseModel):
    """统一结构化题卡中的一个选项对象。"""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_OPTION_CHARS,
        description="用户选择后提交的选项标签",
    )
    description: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_OPTION_DESCRIPTION_CHARS,
        description="解释选项含义的简短说明",
    )

    @field_validator("label", "description")
    @classmethod
    def normalize_option_text(cls, value: str) -> str:
        """去除选项文本两端空白，拒绝空值和多行内容。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("选项标签和说明不能为空")
        if "\n" in normalized or "\r" in normalized:
            raise ValueError("选项标签和说明必须是单行纯文本")
        return normalized


class Question(BaseModel):
    """所有结构化追问共用的严格题目模型。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="稳定且唯一的 snake_case 问题标识",
    )
    title: str = Field(
        min_length=1,
        max_length=100,
        description="包含完整问题内容的单行标题",
    )
    type: Literal["SingleChoice", "MultiChoice"] = Field(
        description="只允许单选题或多选题",
    )
    options: list[QuestionOption] = Field(
        min_length=QUESTION_OPTION_COUNT,
        max_length=QUESTION_OPTION_COUNT,
        description=(
            f"必须提供 {QUESTION_OPTION_COUNT} 个互不重复的选项对象，"
            "每项包含 label 和 description"
        ),
    )
    allow_custom_input: Literal[False] = Field(
        description="固定为 false，不允许选项外的自定义输入",
    )

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """去除题目两端空白，拒绝空值和多行内容。"""
        normalized = value.strip()
        if not normalized or "\n" in normalized or "\r" in normalized:
            raise ValueError("完整问题必须放在非空的单行 title 中")
        return normalized

    @model_validator(mode="after")
    def validate_unique_option_labels(self) -> "Question":
        """确保四个结构化选项的提交标签互不重复。"""
        labels = [option.label for option in self.options]
        if len({label.casefold() for label in labels}) != len(labels):
            raise ValueError("问题选项标签不能重复")
        return self


class QuestionPayload(BaseModel):
    """当前一轮结构化追问的共享载荷。"""

    model_config = ConfigDict(extra="forbid")

    questions: list[Question] = Field(
        min_length=1,
        max_length=MAX_QUESTIONS_PER_BATCH,
        description=f"当前轮的问题，数量为 1–{MAX_QUESTIONS_PER_BATCH} 题",
    )

    @model_validator(mode="after")
    def validate_unique_question_ids(self) -> "QuestionPayload":
        """拒绝同一批次中重复的问题标识。"""
        question_ids = [question.id for question in self.questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("同一批次的问题标识不能重复")
        return self

    def validate_answers(self, answers: dict[str, Any]) -> None:
        """校验新结构化选择题答案是否匹配当前批次。"""
        expected_ids = {question.id for question in self.questions}
        if set(answers) != expected_ids:
            raise ValueError("答案必须与当前问题批次完全匹配")

        for question in self.questions:
            answer = answers[question.id]
            option_labels = {option.label for option in question.options}
            if question.type == "SingleChoice":
                if not isinstance(answer, str) or answer not in option_labels:
                    raise ValueError("单选题答案必须是一个有效选项标签")
                continue

            if (
                not isinstance(answer, list)
                or not answer
                or len(answer) > MAX_QUESTION_SELECTION_COUNT
                or any(
                    not isinstance(item, str)
                    or not item.strip()
                    for item in answer
                )
                or len(answer) != len(set(answer))
                or any(item not in option_labels for item in answer)
            ):
                raise ValueError(
                    f"多选题必须提交 1–{MAX_QUESTION_SELECTION_COUNT} 个"
                    "有效且不重复的选项标签"
                )


def validate_question_batch(
    questions: Sequence[Question | dict[str, Any]],
) -> QuestionPayload:
    """统一校验所有智能体发出的结构化问题批次。"""
    return QuestionPayload.model_validate({"questions": questions})
