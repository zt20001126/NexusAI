"""定义劳动法律 RAG 的法规、版本和条文持久化模型。"""

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from agents.labor_law_agent.constants import LEGAL_EMBEDDING_DIMENSIONS
from app.models.base import Base


class LegalDocument(Base):
    """法规主记录，保存跨版本保持稳定的法律名称和制定机关。"""

    __tablename__ = "legal_documents"
    __table_args__ = (
        UniqueConstraint("title", name="uq_legal_documents_title"),
        {"comment": "全国性劳动法律法规的稳定主记录"},
    )

    document_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False, comment="法规主记录雪花 ID"
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, comment="法规正式名称")
    legal_type: Mapped[str] = mapped_column(Text, nullable=False, comment="法律或行政法规类别")
    issuer: Mapped[str] = mapped_column(Text, nullable=False, comment="法规制定机关")
    jurisdiction: Mapped[str] = mapped_column(
        String(32), nullable=False, default="中国大陆全国", comment="法规适用地域"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="记录创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="记录最近更新时间"
    )


class LegalLawVersion(Base):
    """法规版本记录，保留原始文件摘要、官方来源及现行版本标记。"""

    __tablename__ = "legal_law_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "source_sha256", name="uq_legal_law_versions_source"),
        CheckConstraint(
            "status IN ('effective', 'amended', 'repealed', 'future')",
            name="ck_legal_law_versions_status",
        ),
        Index("idx_legal_law_versions_current", "document_id", "is_current"),
        Index(
            "uq_legal_law_versions_one_current",
            "document_id",
            unique=True,
            postgresql_where=text("is_current IS TRUE"),
        ),
        {"comment": "法律法规的原文版本和生效状态"},
    )

    law_version_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False, comment="法规版本雪花 ID"
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("legal_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        comment="所属法规主记录 ID",
    )
    source_file: Mapped[str] = mapped_column(Text, nullable=False, comment="用于解析的法规文本文件")
    original_file: Mapped[str | None] = mapped_column(
        Text, comment="官方数据库下载的原始文件"
    )
    source_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="解析文件的 SHA-256 摘要"
    )
    original_sha256: Mapped[str | None] = mapped_column(
        String(64), comment="官方原始文件的 SHA-256 摘要"
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False, comment="官方法规详情链接")
    promulgated_on: Mapped[date | None] = mapped_column(Date, comment="法规公布日期")
    effective_on: Mapped[date | None] = mapped_column(Date, comment="法规施行日期")
    status: Mapped[str] = mapped_column(Text, nullable=False, comment="法规时效状态")
    retrieved_on: Mapped[date] = mapped_column(Date, nullable=False, comment="原文获取日期")
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否为当前检索使用的版本"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="版本导入时间"
    )


class LegalArticle(Base):
    """条文级知识记录，保存原文、章节位置和向量检索所需 Embedding。"""

    __tablename__ = "legal_articles"
    __table_args__ = (
        UniqueConstraint("law_version_id", "article_no", name="uq_legal_articles_version_number"),
        Index(
            "idx_legal_articles_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"comment": "按法律条文切分的 RAG 检索知识"},
    )

    article_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False, comment="法条雪花 ID"
    )
    law_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("legal_law_versions.law_version_id", ondelete="CASCADE"),
        nullable=False,
        comment="法条所属法规版本 ID",
    )
    article_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="法条编号")
    chapter: Mapped[str | None] = mapped_column(Text, comment="所属章")
    section: Mapped[str | None] = mapped_column(Text, comment="所属节")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="法条原文")
    embedding: Mapped[list[float]] = mapped_column(
        Vector(LEGAL_EMBEDDING_DIMENSIONS), nullable=False, comment="法条向量表示"
    )

