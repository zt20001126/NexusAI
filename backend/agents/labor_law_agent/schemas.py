"""定义劳动法规解析、检索和模型回答使用的类型边界。"""

from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class ParsedArticle:
    """解析后的单条法规文本及其章节定位。"""

    article_no: str
    chapter: str | None
    section: str | None
    content: str


@dataclass(frozen=True)
class ParsedLegalDocument:
    """法规版本及来源元数据，用于知识库导入和版本追溯。"""

    title: str
    legal_type: str
    issuer: str
    source_file: str
    original_file: str | None
    source_sha256: str
    original_sha256: str | None
    source_url: str
    promulgated_on: str | None
    effective_on: str | None
    retrieved_on: str
    status: str
    articles: list[ParsedArticle]


@dataclass(frozen=True)
class LegalEvidence:
    """检索证据传输对象，隔离 ORM 模型与 RAG 节点。"""

    article_id: str
    title: str
    article_no: str
    chapter: str | None
    section: str | None
    content: str
    source_url: str
    effective_on: str | None
    vector_similarity: float = 0.0
    keyword_matches: int = 0


@dataclass(frozen=True)
class EmbeddedArticle:
    """供法规导入事务保存的法条原文与定长向量。"""

    article: ParsedArticle
    embedding: list[float]


class LegalAnswerClaim(BaseModel):
    """一个可由指定已检索法条支持的回答要点。"""

    text: str = Field(min_length=1, max_length=2_000, description="由已检索法条支持的回答要点")
    article_ids: list[str] = Field(min_length=1, description="支持该要点的已检索法条 ID")


class LegalAnswerDraft(BaseModel):
    """劳动法律模型输出，生成前由检索证据限定可引用范围。"""

    claims: list[LegalAnswerClaim] = Field(max_length=12, description="可由检索法条支持的回答要点")
    unanswered_aspects: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="知识库当前不能由已检索条文支持的问题部分",
    )

