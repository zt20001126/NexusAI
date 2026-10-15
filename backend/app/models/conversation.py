"""定义智能体会话的数据库持久化模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Conversation(Base):
    """会话模型，保存所有者、智能体、标题及会话时间信息。"""

    __tablename__ = "conversations"
    __table_args__ = (
        Index(
            "idx_conversations_owner_updated",
            "owner_id",
            text("updated_at DESC"),
        ),
        {"comment": "智能体对话会话"},
    )

    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        comment="会话雪花 ID",
    )
    owner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user_identities.user_id"),
        nullable=False,
        comment="会话所有者的内部用户 ID",
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="会话所属智能体的稳定数据库 ID"
    )
    title: Mapped[str | None] = mapped_column(Text, comment="会话展示标题")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="会话创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="会话最近更新时间",
    )
