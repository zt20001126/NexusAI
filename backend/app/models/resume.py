"""定义单人简历内容与排版设置的 ORM 持久化模型。"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Resume(Base):
    """每个内部用户最多保存一份 JSONB 简历。"""

    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("owner_id", name="uq_resumes_owner_id"),
        CheckConstraint("jsonb_typeof(content) = 'object'", name="ck_resumes_content_object"),
        CheckConstraint(
            "jsonb_typeof(style_config) = 'object'",
            name="ck_resumes_style_config_object",
        ),
        {"comment": "简历助手保存的简历内容和排版设置"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        comment="简历所有者，关联 users.user_id",
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    style_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
