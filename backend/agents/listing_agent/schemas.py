"""Listing 图片识别、信息追问和输出 JSON 的边界模型。"""

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.constants import MAX_QUESTIONS_PER_BATCH, MAX_REFERENCE_IMAGE_COUNT
from agent.schemas.question import Question, validate_question_batch
from agents.listing_agent.constants import (
    LISTING_SCHEMA_VERSION,
    LISTING_VERSION_COUNT,
    MAX_LISTING_ATTRIBUTES,
    MAX_LISTING_DESCRIPTION_CHARS,
    MAX_LISTING_KEYWORDS,
    MAX_LISTING_PRODUCT_FACTS,
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


class ListingPlan(BaseModel):
    """模型根据图片和商家资料判断必要信息缺口。"""

    model_config = ConfigDict(extra="forbid")

    product_facts: dict[str, str] = Field(
        default_factory=dict,
        max_length=MAX_LISTING_PRODUCT_FACTS,
    )
    questions: list[Question] = Field(
        default_factory=list,
        max_length=MAX_QUESTIONS_PER_BATCH,
    )

    @field_validator("questions")
    @classmethod
    def validate_question_batch(cls, questions: list[Question]) -> list[Question]:
        """Listing 计划使用共享入口校验每个非空问题批次。"""
        if questions:
            return validate_question_batch(questions).questions
        return questions


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
    ] = Field(max_length=MAX_LISTING_ATTRIBUTES)

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

    questions: list[Question] = Field(
        min_length=1,
        max_length=MAX_QUESTIONS_PER_BATCH,
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

    @field_validator("questions")
    @classmethod
    def validate_question_batch(cls, questions: list[Question]) -> list[Question]:
        """Listing 追问工具输入再次复用共享问题批次校验。"""
        return validate_question_batch(questions).questions


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
