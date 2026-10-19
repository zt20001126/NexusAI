"""定义不同智能体共用的任务结果数据库模型。"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaskResult(Base):
    """任务结果模型，按会话归属并保存状态与 JSON 数据。"""

    __tablename__ = "task_results"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('pending', 'awaiting_input', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_task_results_status",
        ),
        Index("idx_task_results_conversation_created", "conversation_id", "created_at"),
        Index("idx_task_results_message", "message_id"),
        {"comment": "所有智能体共享的任务结果及 OSS 对象元数据"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        comment="任务结果雪花 ID",
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        comment="任务所属会话 ID",
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("messages.message_id", ondelete="SET NULL"),
        comment="任务结果关联的助手消息 ID",
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, comment="任务生命周期状态"
    )
    input: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="任务输入、参数和参考图 OSS 对象元数据",
    )
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="生成结果 OSS 对象元数据及智能体扩展数据",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="任务结果创建时间",
    )
