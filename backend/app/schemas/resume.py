"""简历助手的持久化与 HTTP DTO 契约。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


MAX_EDUCATIONS = 10
MAX_SKILLS = 20
MAX_WORKS = 20
MAX_PROJECTS = 20
MAX_SKILL_CHARS = 500
MAX_RICH_TEXT_CHARS = 4_000
MAX_TOTAL_RICH_TEXT_CHARS = 20_000
MAX_RESUME_JSON_NODES = 2_000
MAX_RESUME_JSON_BYTES = 256 * 1024
MAX_TIPTAP_DEPTH = 32
MAX_RESUME_PHOTO_BYTES = 5 * 1024 * 1024
MAX_RESUME_PHOTO_REQUEST_BYTES = 6 * 1024 * 1024

_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHOTO_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class StrictModel(BaseModel):
    """拒绝未声明字段，并让字符串 DTO 保持 JSON 原始类型。"""

    model_config = ConfigDict(extra="forbid")


class BasicInfo(StrictModel):
    name: Annotated[StrictStr, Field(max_length=80)] = ""
    phone: Annotated[StrictStr, Field(max_length=32)] = ""
    email: Annotated[StrictStr, Field(max_length=254)] = ""
    intended_position: Annotated[StrictStr, Field(max_length=120)] = ""
    birth_month: Annotated[StrictStr, Field(max_length=7)] | None = None
    photo_id: Annotated[StrictStr, Field(pattern=_PHOTO_ID_PATTERN.pattern)] | None = None

    @field_validator("birth_month")
    @classmethod
    def validate_birth_month(cls, value: str | None) -> str | None:
        """校验出生年月格式。"""
        if value is not None and not _MONTH_PATTERN.fullmatch(value):
            raise ValueError("月份必须采用 YYYY-MM 格式")
        return value


class EducationItem(StrictModel):
    id: UUID
    school: Annotated[StrictStr, Field(max_length=120)]
    major: Annotated[StrictStr, Field(max_length=120)] = ""
    degree: Annotated[StrictStr, Field(max_length=120)] = ""
    start_month: Annotated[StrictStr, Field(max_length=7)]
    end_month: Annotated[StrictStr, Field(max_length=7)]

    @field_validator("start_month", "end_month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        """校验年月格式。"""
        if not _MONTH_PATTERN.fullmatch(value):
            raise ValueError("月份必须采用 YYYY-MM 格式")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> EducationItem:
        """保证教育经历起止月份合法。"""
        if self.start_month > self.end_month:
            raise ValueError("开始月份不能晚于结束月份")
        if not self.school.strip():
            raise ValueError("学校名称不能为空")
        return self


class TiptapMark(StrictModel):
    type: Literal["bold", "italic", "underline"]


class TiptapText(StrictModel):
    type: Literal["text"]
    text: StrictStr
    marks: list[TiptapMark] | None = None


class TiptapHardBreak(StrictModel):
    type: Literal["hardBreak"]


class TiptapParagraph(StrictModel):
    type: Literal["paragraph"]
    content: list[TiptapText | TiptapHardBreak] = Field(default_factory=list)


class TiptapListItem(StrictModel):
    type: Literal["listItem"]
    content: list["TiptapParagraph | TiptapBulletList | TiptapOrderedList"]


class TiptapBulletList(StrictModel):
    type: Literal["bulletList"]
    content: list[TiptapListItem]


class OrderedListAttributes(StrictModel):
    start: int = Field(default=1, ge=1, le=1_000)


class TiptapOrderedList(StrictModel):
    type: Literal["orderedList"]
    attrs: OrderedListAttributes | None = None
    content: list[TiptapListItem]


TiptapListItem.model_rebuild()


class TiptapDocument(StrictModel):
    type: Literal["doc"] = "doc"
    content: list[TiptapParagraph | TiptapBulletList | TiptapOrderedList]

    @model_validator(mode="before")
    @classmethod
    def validate_raw_depth(cls, value: object) -> object:
        """在构造递归 Pydantic 节点前限制输入深度，避免极深 JSON 消耗栈。"""
        if _max_json_depth(value) > MAX_TIPTAP_DEPTH:
            raise ValueError("Tiptap 文档嵌套深度超过上限")
        return value

    @model_validator(mode="after")
    def validate_document_size(self) -> TiptapDocument:
        """限制单个 Tiptap 文档的节点数和正文长度。"""
        serialized = self.model_dump(mode="python")
        if _count_json_nodes(serialized) > MAX_RESUME_JSON_NODES:
            raise ValueError("富文本节点数量超过上限")
        if sum(len(value) for value in _text_values(serialized)) > MAX_RICH_TEXT_CHARS:
            raise ValueError("单条富文本超过 4,000 个字符")
        return self


class WorkItem(StrictModel):
    id: UUID
    company: Annotated[StrictStr, Field(max_length=120)]
    position: Annotated[StrictStr, Field(max_length=120)]
    start_month: Annotated[StrictStr, Field(max_length=7)]
    end_month: Annotated[StrictStr, Field(max_length=7)]
    content: TiptapDocument

    @field_validator("start_month", "end_month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        """校验年月格式。"""
        if not _MONTH_PATTERN.fullmatch(value):
            raise ValueError("月份必须采用 YYYY-MM 格式")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> WorkItem:
        """校验工作经历必填字段与月份范围。"""
        if self.start_month > self.end_month:
            raise ValueError("开始月份不能晚于结束月份")
        if not self.company.strip() or not self.position.strip():
            raise ValueError("公司和职位不能为空")
        return self


class ProjectItem(StrictModel):
    id: UUID
    name: Annotated[StrictStr, Field(max_length=120)]
    role: Annotated[StrictStr, Field(max_length=80)] = ""
    technology_stack: Annotated[StrictStr, Field(max_length=240)] = ""
    start_month: Annotated[StrictStr, Field(max_length=7)]
    end_month: Annotated[StrictStr, Field(max_length=7)]
    content: TiptapDocument

    @field_validator("start_month", "end_month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        """校验年月格式。"""
        if not _MONTH_PATTERN.fullmatch(value):
            raise ValueError("月份必须采用 YYYY-MM 格式")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> ProjectItem:
        """校验项目名称与月份范围。"""
        if self.start_month > self.end_month:
            raise ValueError("开始月份不能晚于结束月份")
        if not self.name.strip():
            raise ValueError("项目名称不能为空")
        return self


SkillText = Annotated[StrictStr, Field(max_length=MAX_SKILL_CHARS)]


class ResumeContent(StrictModel):
    basic_info: BasicInfo = Field(default_factory=BasicInfo)
    educations: list[EducationItem] = Field(default_factory=list, max_length=MAX_EDUCATIONS)
    skills: list[SkillText] = Field(default_factory=list, max_length=MAX_SKILLS)
    works: list[WorkItem] = Field(default_factory=list, max_length=MAX_WORKS)
    projects: list[ProjectItem] = Field(default_factory=list, max_length=MAX_PROJECTS)

    @model_validator(mode="after")
    def validate_content(self) -> ResumeContent:
        """验证结构化条目 UUID 唯一及全简历资源上限。"""
        for field_name in ("educations", "works", "projects"):
            identifiers = [str(item.id) for item in getattr(self, field_name)]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{field_name} 中的条目 ID 不能重复")

        rich_text_length = sum(
            sum(len(value) for value in _text_values(item.content.model_dump(mode="python")))
            for item in [*self.works, *self.projects]
        )
        if rich_text_length > MAX_TOTAL_RICH_TEXT_CHARS:
            raise ValueError("工作和项目富文本总量超过 20,000 个字符")
        if _count_json_nodes(self.model_dump(mode="python")) > MAX_RESUME_JSON_NODES:
            raise ValueError("简历 JSON 节点数量超过上限")
        return self


class PageMargin(StrictModel):
    top: int = Field(default=14, ge=5, le=30)
    right: int = Field(default=14, ge=5, le=30)
    bottom: int = Field(default=14, ge=5, le=30)
    left: int = Field(default=14, ge=5, le=30)


class ResumeStyleConfig(StrictModel):
    font_family: Literal["wenquanyi_zenhei", "arphic_ukai"] = "wenquanyi_zenhei"
    font_size_pt: int = Field(default=10, ge=8, le=14)
    line_height: float = Field(default=1.4, ge=1.0, le=2.0)
    paragraph_spacing_pt: int = Field(default=4, ge=0, le=12)
    section_spacing_pt: int = Field(default=12, ge=4, le=24)
    page_margin_mm: PageMargin = Field(default_factory=PageMargin)
    heading_color: Annotated[StrictStr, Field(pattern=_COLOR_PATTERN.pattern)] = "#1677FF"
    divider_color: Annotated[StrictStr, Field(pattern=_COLOR_PATTERN.pattern)] = "#1677FF"
    divider_width_pt: float = Field(default=1, ge=0.5, le=3)


class ResumeSaveRequest(StrictModel):
    content: ResumeContent
    style_config: ResumeStyleConfig

    @model_validator(mode="after")
    def validate_required_contact(self) -> ResumeSaveRequest:
        """未保存简历可保持空白，但实际保存时要求姓名、电话和邮箱。"""
        info = self.content.basic_info
        if not info.name.strip() or not info.phone.strip():
            raise ValueError("姓名和电话不能为空")
        if not _EMAIL_PATTERN.fullmatch(info.email):
            raise ValueError("邮箱格式不正确")
        return self


class ResumeResponse(StrictModel):
    exists: bool
    content: ResumeContent
    style_config: ResumeStyleConfig
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResumePhotoUploadResponse(StrictModel):
    photo_id: Annotated[StrictStr, Field(pattern=_PHOTO_ID_PATTERN.pattern)]
    mime_type: Literal["image/png", "image/jpeg"]
    file_size: int = Field(ge=1, le=MAX_RESUME_PHOTO_BYTES)


def _count_json_nodes(value: object) -> int:
    """递归计算 JSON 中对象、数组和标量节点数。"""
    if isinstance(value, dict):
        return 1 + sum(_count_json_nodes(item) for item in value.values())
    if isinstance(value, list):
        return 1 + sum(_count_json_nodes(item) for item in value)
    return 1


def _max_json_depth(value: object, depth: int = 0) -> int:
    """返回嵌套 JSON 的最大容器深度。"""
    if isinstance(value, dict):
        return max(
            (_max_json_depth(item, depth + 1) for item in value.values()),
            default=depth + 1,
        )
    if isinstance(value, list):
        return max(
            (_max_json_depth(item, depth + 1) for item in value),
            default=depth + 1,
        )
    return depth


def _text_values(value: object) -> list[str]:
    """递归提取 Tiptap JSON 中所有文本节点。"""
    if isinstance(value, dict):
        text = value.get("text")
        own = [text] if isinstance(text, str) else []
        return own + [part for item in value.values() for part in _text_values(item)]
    if isinstance(value, list):
        return [part for item in value for part in _text_values(item)]
    return []
