"""定义智能体会话的数据库持久化模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from agent.enums import AgentType

from app.models.base import Base

_AGENT_TYPE_SQL_VALUES = ", ".join(f"'{agent.value}'" for agent in AgentType)


class Conversation(Base):
    """会话模型，保存所有者、智能体、标题及会话时间信息。"""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            f"agent IN ({_AGENT_TYPE_SQL_VALUES})",
            name="ck_conversations_agent_type",
        ),
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
        ForeignKey("users.user_id"),
        nullable=False,
        comment="会话所有者的内部用户 ID",
    )
    agent: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="会话所属智能体的字符串枚举值",
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
