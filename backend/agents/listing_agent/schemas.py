"""Listing 图片识别、信息追问和输出 JSON 的边界模型。"""

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.constants import MAX_QUESTION_OPTION_CHARS, MAX_REFERENCE_IMAGE_COUNT
from agent.schemas.question import Question
from agents.listing_agent.constants import (
    LISTING_SCHEMA_VERSION,
    LISTING_VERSION_COUNT,
    LISTING_QUESTION_OPTION_COUNT,
    MAX_LISTING_ATTRIBUTES,
    MAX_LISTING_DESCRIPTION_CHARS,
    MAX_LISTING_KEYWORDS,
    MAX_LISTING_PRODUCT_FACTS,
    MAX_LISTING_QUESTION_COUNT,
    MAX_LISTING_SELLING_POINTS,
    MAX_LISTING_TITLE_CHARS,
    MIN_LISTING_KEYWORDS,
    MIN_LISTING_SELLING_POINTS,
)


class ListingImageAnalysis(BaseModel):
    """视觉模型识别出的图片可见特征和包装文字。"""

    model_config = ConfigDict(extra="forbid")

    candidate_category: str = Field(max_length=200)
    visible_features: list[Annotated[str, Field(max_length=500)]] = Field(
        default_factory=list,
        max_length=40,
    )
    packaging_text: list[Annotated[str, Field(max_length=500)]] = Field(
        default_factory=list,
        max_length=60,
    )
    visible_claims: list[Annotated[str, Field(max_length=500)]] = Field(
        default_factory=list,
        max_length=30,
    )
    uncertain_observations: list[Annotated[str, Field(max_length=500)]] = Field(
        default_factory=list,
        max_length=30,
    )


class ListingQuestion(Question):
    """Listing 只接受恰好四个选项且不提供自定义输入的选择题。"""

    type: Literal["SingleChoice", "MultiChoice"] = Field(
        default="SingleChoice",
        description="只允许单选题或多选题",
    )
    options: list[
        Annotated[
            str,
            Field(min_length=1, max_length=MAX_QUESTION_OPTION_CHARS),
        ]
    ] = Field(
        min_length=LISTING_QUESTION_OPTION_COUNT,
        max_length=LISTING_QUESTION_OPTION_COUNT,
        description=f"必须提供 {LISTING_QUESTION_OPTION_COUNT} 个互不重复的选项",
    )
    allow_custom_input: Literal[False] = Field(
        default=False,
        description="不允许用户输入选项之外的内容",
    )


class ListingPlan(BaseModel):
    """模型根据图片和商家资料判断必要信息缺口。"""

    model_config = ConfigDict(extra="forbid")

    product_facts: dict[str, str] = Field(
        default_factory=dict,
        max_length=MAX_LISTING_PRODUCT_FACTS,
    )
    questions: list[ListingQuestion] = Field(
        default_factory=list,
        max_length=MAX_LISTING_QUESTION_COUNT,
    )

    @model_validator(mode="after")
    def validate_question_ids(self) -> "ListingPlan":
        """保持问题标识稳定且唯一。"""
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("追问问题标识不能重复")
        if any(
            re.fullmatch(r"[a-z][a-z0-9_]{0,63}", question_id) is None
            for question_id in ids
        ):
            raise ValueError("追问问题标识必须使用 snake_case")
        return self


class ListingVersion(BaseModel):
    """一个可供商家选择的完整 Listing 版本。"""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, le=LISTING_VERSION_COUNT)
    title: str = Field(min_length=1, max_length=MAX_LISTING_TITLE_CHARS)
    selling_points: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        min_length=MIN_LISTING_SELLING_POINTS,
        max_length=MAX_LISTING_SELLING_POINTS,
    )
    description: str = Field(min_length=1, max_length=MAX_LISTING_DESCRIPTION_CHARS)
    keywords: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        min_length=MIN_LISTING_KEYWORDS,
        max_length=MAX_LISTING_KEYWORDS,
    )
    product_attributes: dict[
        Annotated[str, Field(min_length=1, max_length=100)],
        Annotated[str, Field(min_length=1, max_length=500)],
    ] = Field(
        min_length=1,
        max_length=MAX_LISTING_ATTRIBUTES,
    )

    @field_validator("description")
    @classmethod
    def validate_plain_text(cls, value: str) -> str:
        """拒绝 Markdown、HTML 等富文本标记，保留普通段落换行。"""
        text = value.strip()
        markdown_line = re.compile(r"(?m)^\s*(?:#{1,6}\s|[-*+]\s|>\s|\d+[.)]\s)")
        if (
            "```" in text
            or "**" in text
            or "__" in text
            or re.search(r"<[^>]+>", text)
            or markdown_line.search(text)
        ):
            raise ValueError("详情描述必须是纯文本")
        return text


class ListingResult(BaseModel):
    """可持久化的完整多版本 JSON 结果。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[LISTING_SCHEMA_VERSION] = LISTING_SCHEMA_VERSION
    product_facts: dict[str, str] = Field(max_length=MAX_LISTING_PRODUCT_FACTS)
    image_analysis: ListingImageAnalysis
    versions: list[ListingVersion] = Field(
        min_length=LISTING_VERSION_COUNT,
        max_length=LISTING_VERSION_COUNT,
    )

    @model_validator(mode="after")
    def validate_version_numbers(self) -> "ListingResult":
        """确保三个版本编号连续且固定。"""
        if [item.version for item in self.versions] != list(
            range(1, LISTING_VERSION_COUNT + 1)
        ):
            raise ValueError("Listing 必须按顺序包含版本 1、2、3")
        return self


class AskListingQuestionsInput(BaseModel):
    """追问工具接收问题和可信的运行身份。"""

    model_config = ConfigDict(extra="forbid")

    questions: list[ListingQuestion] = Field(
        min_length=1,
        max_length=MAX_LISTING_QUESTION_COUNT,
    )
    task_result_id: str = Field(min_length=1, max_length=64)
    principal_id: str = Field(min_length=1, max_length=256)
    conversation_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=64)
    original_request: str = Field(max_length=20_000)
    attachment_ids: list[str] = Field(max_length=MAX_REFERENCE_IMAGE_COUNT)
    image_analysis: ListingImageAnalysis
    product_facts: dict[str, str] = Field(max_length=MAX_LISTING_PRODUCT_FACTS)
    confirmed_answers: dict[str, Any] = Field(max_length=20)


class SaveListingResultInput(BaseModel):
    """结果工具接收校验过的输出和服务端运行身份。"""

    model_config = ConfigDict(extra="forbid")

    task_result_id: str = Field(min_length=1, max_length=64)
    principal_id: str = Field(min_length=1, max_length=256)
    conversation_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=64)
    original_request: str = Field(max_length=20_000)
    attachment_ids: list[str] = Field(max_length=MAX_REFERENCE_IMAGE_COUNT)
    confirmed_answers: dict[str, Any] = Field(max_length=20)
    listing_result: ListingResult
