"""定义智能体运行记录的数据库持久化模型。"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentRun(Base):
    """智能体运行模型，保存运行状态、所属会话及恢复元数据。"""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'waiting', 'completed', 'cancelled', 'failed')",
            name="ck_agent_runs_status",
        ),
        Index("idx_agent_runs_conversation_id", "conversation_id"),
        {"comment": "智能体运行状态与恢复信息"},
    )

    run_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        comment="运行雪花 ID",
    )
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        comment="运行所属会话 ID",
    )
    agent_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="运行所属智能体的稳定数据库 ID"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, comment="运行生命周期状态")
    run_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="追问恢复及运行上下文元数据",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="运行创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="运行最近更新时间",
    )
