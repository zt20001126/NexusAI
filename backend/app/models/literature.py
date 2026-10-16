"""定义文献解读助手的文献元数据、证据分块和会话文献关系。"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from agents.literature_reader_agent.constants import LITERATURE_EMBEDDING_DIMENSIONS
from app.models.base import Base


class LiteratureDocument(Base):
    """文献持久化模型，保存 PDF 元数据、OSS 对象位置和处理生命周期。"""

    __tablename__ = "literature_documents"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('pdf_upload', 'pdf_url', 'web_url')",
            name="ck_literature_documents_source_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed')",
            name="ck_literature_documents_status",
        ),
        Index("idx_literature_documents_owner_updated", "owner_id", text("updated_at DESC")),
        {"comment": "文献解读助手的用户文献元数据及处理状态"},
    )

    document_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False, comment="文献雪花 ID"
    )
    owner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user_identities.user_id", ondelete="CASCADE"),
        nullable=False,
        comment="文献所有者的内部用户 ID",
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, comment="文献标题或用户可见名称")
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="来源类型")
    source_url: Mapped[str | None] = mapped_column(Text, comment="兼容既有链接来源记录的 URL")
    file_name: Mapped[str | None] = mapped_column(Text, comment="上传 PDF 文件名")
    object_key: Mapped[str | None] = mapped_column(Text, comment="私有 OSS 中的 PDF 对象键")
    content_type: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="PDF 媒体类型或既有来源记录的媒体类型"
    )
    file_size: Mapped[int | None] = mapped_column(BigInteger, comment="来源内容字节数")
    content_sha256: Mapped[str | None] = mapped_column(
        String(64), comment="导入内容的 SHA-256 摘要"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="queued", comment="文献处理状态"
    )
    error_code: Mapped[str | None] = mapped_column(String(64), comment="稳定的导入失败代码")
    error_message: Mapped[str | None] = mapped_column(Text, comment="面向用户的安全错误说明")
    page_count: Mapped[int | None] = mapped_column(Integer, comment="PDF 实际页数")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="文献创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="文献最近更新时间",
    )


class LiteratureChunk(Base):
    """文献分块持久化模型，保存原文、引用定位和 pgvector 表示。"""

    __tablename__ = "literature_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_literature_chunks_document_index"),
        Index("idx_literature_chunks_document", "document_id"),
        Index(
            "idx_literature_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"comment": "文献原文分块及向量检索记录"},
    )

    chunk_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False, comment="证据分块雪花 ID"
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("literature_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        comment="所属文献 ID",
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="文献内分块序号")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="文献原文片段")
    chapter: Mapped[str | None] = mapped_column(Text, comment="可识别的所属章")
    section: Mapped[str | None] = mapped_column(Text, comment="可识别的所属节")
    page_start: Mapped[int | None] = mapped_column(Integer, comment="PDF 起始页码，一基")
    page_end: Mapped[int | None] = mapped_column(Integer, comment="PDF 结束页码，一基")
    paragraph_start: Mapped[int | None] = mapped_column(Integer, comment="页内起始段落序号，一基")
    paragraph_end: Mapped[int | None] = mapped_column(Integer, comment="页内结束段落序号，一基")
    embedding: Mapped[list[float]] = mapped_column(
        Vector(LITERATURE_EMBEDDING_DIMENSIONS),
        nullable=False,
        comment="由配置的文献 Embedding 模型生成的向量",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="分块创建时间"
    )


class LiteratureConversationDocument(Base):
    """会话文献关系模型，供历史文献对话恢复选中文献范围。"""

    __tablename__ = "literature_conversation_documents"
    __table_args__ = (
        {"comment": "文献解读助手会话当前关联的文献集合"},
    )

    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        primary_key=True,
        comment="文献会话 ID",
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("literature_documents.document_id", ondelete="CASCADE"),
        primary_key=True,
        comment="会话关联的文献 ID",
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="关系创建时间"
    )

