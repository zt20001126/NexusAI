"""定义会话消息的数据库持久化模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Message(Base):
    """消息模型，保存用户消息和助手回复的顺序及文本内容。"""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        UniqueConstraint("conversation_id", "sequence", name="uq_messages_conversation_sequence"),
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
    run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("agent_runs.run_id", ondelete="SET NULL"),
        comment="生成该消息的运行 ID",
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="会话内消息顺序")
    role: Mapped[str] = mapped_column(Text, nullable=False, comment="消息角色")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息文本内容")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="消息创建时间",
    )
