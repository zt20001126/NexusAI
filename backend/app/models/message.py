"""定义会话消息的数据库持久化模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base


class Message(Base):
    """消息模型，以 JSON 内容块保存用户消息和助手回复。"""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        {"comment": "会话中的用户消息和助手回复"},
    )

    message_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        comment="消息雪花 ID",
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        comment="消息所属会话 ID",
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, comment="消息角色")
    content: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {"blocks": []},
        server_default='{"blocks": []}',
        comment="消息内容块",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="消息创建时间",
    )
