"""文献助手 HTTP 请求和响应数据结构。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.literature_reader_agent.constants import LITERATURE_AGENT_MAX_DOCUMENTS


DocumentStatus = Literal["queued", "processing", "ready", "failed"]
# 旧链接导入记录仍会返回历史来源类型；新建记录只由 PDF 上传接口创建。
DocumentSourceType = Literal["pdf_upload", "pdf_url", "web_url"]


class LiteratureDocumentSummary(BaseModel):
    """文献库列表和状态查询的公开文献摘要。"""

    model_config = ConfigDict(from_attributes=True)

    document_id: str = Field(description="文献雪花 ID")
    title: str = Field(description="文献标题或用户可见名称")
    source_type: DocumentSourceType = Field(description="文献来源类型")
    source_url: str | None = Field(description="既有链接来源文献的原始链接")
    file_name: str | None = Field(description="上传文件名")
    status: DocumentStatus = Field(description="文献处理状态")
    error_code: str | None = Field(description="稳定的处理失败代码")
    error_message: str | None = Field(description="面向用户的安全错误说明")
    page_count: int | None = Field(description="PDF 页数")
    created_at: datetime = Field(description="文献创建时间")
    updated_at: datetime = Field(description="文献最近更新时间")


class DocumentCreatedResponse(BaseModel):
    """PDF 文献上传成功后返回的队列信息。"""

    document_id: str = Field(description="新建文献雪花 ID")
    status: DocumentStatus = Field(description="当前文献处理状态")


class LiteratureChatRequest(BaseModel):
    """向文献助手提问并限定当前文献范围。"""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=20_000, description="本轮文献问题")
    conversation_id: str | None = Field(
        default=None,
        pattern=r"^[1-9][0-9]{0,18}$",
        description="继续对话时使用的会话雪花 ID",
    )
    document_ids: list[str] | None = Field(
        default=None,
        max_length=LITERATURE_AGENT_MAX_DOCUMENTS,
        description="本轮使用的文献 ID；省略时从已有会话恢复",
    )
    request_id: str = Field(
        min_length=16,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="本轮文献提问的幂等请求标识",
    )

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, values: list[str] | None) -> list[str] | None:
        """校验文献 ID 格式并拒绝重复选择。"""
        if values is None:
            return None
        if not values:
            raise ValueError("至少选择一篇已就绪文献")
        if any(not value.isdigit() or value.startswith("0") for value in values):
            raise ValueError("文献 ID 必须是正整数")
        if len(set(values)) != len(values):
            raise ValueError("文献 ID 不能重复")
        return values


class LiteratureDocumentsResponse(BaseModel):
    """文献列表分页响应。"""

    items: list[LiteratureDocumentSummary] = Field(description="当前页文献")
    limit: int = Field(description="每页数量")
    offset: int = Field(description="当前页偏移量")
    has_more: bool = Field(description="是否还有后续文献")


class ConversationLiteratureDocumentsResponse(BaseModel):
    """历史会话当前关联的文献摘要。"""

    document_ids: list[str] = Field(description="会话关联文献 ID")
    documents: list[LiteratureDocumentSummary] = Field(description="会话关联文献")


class UpdateConversationLiteratureDocumentsRequest(BaseModel):
    """更新历史会话关联文献的请求参数。"""

    document_ids: list[str] = Field(
        max_length=LITERATURE_AGENT_MAX_DOCUMENTS,
        description="替换为该会话使用的文献 ID",
    )

    @field_validator("document_ids")
    @classmethod
    def validate_unique_document_ids(cls, values: list[str]) -> list[str]:
        """拒绝重复选择，保持会话文献关系确定。"""
        if len(set(values)) != len(values):
            raise ValueError("文献 ID 不能重复")
        return values


__all__ = [
    "ConversationLiteratureDocumentsResponse",
    "DocumentCreatedResponse",
    "DocumentSourceType",
    "DocumentStatus",
    "LiteratureChatRequest",
    "LiteratureDocumentSummary",
    "LiteratureDocumentsResponse",
    "UpdateConversationLiteratureDocumentsRequest",
]
