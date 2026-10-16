"""定义文献导入、解析、检索和回答各层使用的类型边界。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.literature_reader_agent.constants import (
    LITERATURE_EVIDENCE_QUOTE_MAX_CHARS,
    LITERATURE_ANSWER_MAX_CLAIMS,
)


DocumentStatus = Literal["queued", "processing", "ready", "failed"]
# 保留旧链接导入记录的类型以兼容已有文献；新入库流程只生成 pdf_upload。
DocumentSourceType = Literal["pdf_upload", "pdf_url", "web_url"]


@dataclass(frozen=True)
class LiteratureDocumentRecord:
    """文献仓储传输记录，包含导入任务所需的可信主体和 OSS 元数据。"""

    document_id: str
    owner_principal: str
    title: str
    source_type: DocumentSourceType
    source_url: str | None
    file_name: str | None
    object_key: str | None
    content_type: str
    file_size: int | None
    content_sha256: str | None
    status: DocumentStatus
    error_code: str | None
    error_message: str | None
    page_count: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ParsedSegment:
    """解析出的正文段落及其可用章节、页码和段落定位。"""

    content: str
    chapter: str | None
    section: str | None
    page_number: int | None
    paragraph_number: int | None


@dataclass(frozen=True)
class ParsedLiterature:
    """文献解析结果，不包含持久化 ORM 对象。"""

    title: str
    content_type: str
    segments: list[ParsedSegment]
    page_count: int | None
    is_pdf: bool


@dataclass(frozen=True)
class LiteratureChunkData:
    """保留原文和引用位置的检索分块传输对象。"""

    chunk_index: int
    content: str
    chapter: str | None
    section: str | None
    page_start: int | None
    page_end: int | None
    paragraph_start: int | None
    paragraph_end: int | None


@dataclass(frozen=True)
class EmbeddedLiteratureChunk:
    """待写入数据库的文献分块与定长向量。"""

    chunk: LiteratureChunkData
    embedding: list[float]


@dataclass(frozen=True)
class LiteratureEvidence:
    """检索证据传输对象，隔离 SQLAlchemy 模型与智能体图状态。"""

    evidence_id: str
    document_id: str
    title: str
    source_type: str
    source_url: str | None
    chapter: str | None
    section: str | None
    page_start: int | None
    page_end: int | None
    paragraph_start: int | None
    paragraph_end: int | None
    content: str
    vector_similarity: float = 0.0
    keyword_matches: int = 0


@dataclass(frozen=True)
class LiteratureRetrievalResult:
    """按文献分组的证据和充分性判断。"""

    evidence: list[LiteratureEvidence]
    sufficient_document_ids: frozenset[str]


class LiteratureEvidenceQuote(BaseModel):
    """模型提交的原文逐字摘录，服务端会确认其属于对应检索分块。"""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, description="本轮检索证据 ID")
    quote: str = Field(
        min_length=1,
        max_length=LITERATURE_EVIDENCE_QUOTE_MAX_CHARS,
        description="从对应证据原文逐字复制的片段",
    )


class LiteratureAnswerClaim(BaseModel):
    """一条必须由检索到的原文证据支持的事实陈述。"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2_000, description="可由文献原文支持的事实")
    evidence_quotes: list[LiteratureEvidenceQuote] = Field(
        min_length=1,
        description="支持该事实的原文摘录及对应证据 ID",
    )


class LiteratureAnswerDraft(BaseModel):
    """模型输出的结构化回答草稿，引用由服务端校验和渲染。"""

    model_config = ConfigDict(extra="forbid")

    claims: list[LiteratureAnswerClaim] = Field(
        max_length=LITERATURE_ANSWER_MAX_CLAIMS,
        description="可由检索证据支持的事实陈述",
    )
class LiteratureClaimSupport(BaseModel):
    """核验器对某一回答陈述与原文证据支持关系的判断。"""

    model_config = ConfigDict(extra="forbid")

    claim_index: int = Field(ge=0, description="待核验陈述在草稿中的从零开始序号")
    supported: bool = Field(description="引用的原文是否直接支持该陈述")


class LiteratureSupportDraft(BaseModel):
    """模型输出的结构化原文支持关系核验结果。"""

    model_config = ConfigDict(extra="forbid")

    claims: list[LiteratureClaimSupport] = Field(
        max_length=LITERATURE_ANSWER_MAX_CLAIMS,
        description="每条陈述的原文支持判断",
    )


__all__ = [
    "LiteratureAnswerDraft",
    "LiteratureChunkData",
    "LiteratureDocumentRecord",
    "LiteratureEvidence",
    "LiteratureEvidenceQuote",
    "LiteratureRetrievalResult",
    "ParsedLiterature",
    "ParsedSegment",
]
