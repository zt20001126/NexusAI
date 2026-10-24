"""定义用户积分余额与不可变积分明细的数据库模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.credit_constants import (
    CHAT_MESSAGE_CREDIT_COST,
    CREDIT_EVENT_TOP_UP,
    REGISTRATION_CREDIT_GRANT,
)
from app.models.base import Base


class UserCredit(Base):
    """保存每个用户当前积分余额及 Redis 缓存版本。"""

    __tablename__ = "user_credits"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_user_credits_balance_nonnegative"),
        CheckConstraint("version >= 0", name="ck_user_credits_version_nonnegative"),
        {"comment": "用户积分余额"},
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
        comment="积分所有者的内部用户 ID",
    )
    balance: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
        comment="当前可用积分余额",
    )
    version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
        comment="余额单调递增版本，用于 Redis 更新排序",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="余额最近变更时间",
    )


class CreditEntry(Base):
    """记录注册赠送、对话扣费和运行退款，供审计与幂等核对。"""

    __tablename__ = "credit_entries"
    __table_args__ = (
        CheckConstraint(
            f"(kind = 'registration_grant' AND delta = {REGISTRATION_CREDIT_GRANT}) OR "
            f"(kind = 'message_debit' AND delta = {-CHAT_MESSAGE_CREDIT_COST}) OR "
            f"(kind = 'run_refund' AND delta = {CHAT_MESSAGE_CREDIT_COST}) OR "
            f"(kind = '{CREDIT_EVENT_TOP_UP}' AND delta > 0)",
            name="ck_credit_entries_kind_delta",
        ),
        Index("idx_credit_entries_user_created", "user_id", "created_at"),
        Index("idx_credit_entries_run_kind", "run_id", "kind"),
        {"comment": "用户积分变更不可变明细"},
    )

    event_key: Mapped[str] = mapped_column(
        Text, primary_key=True, comment="业务事件幂等键"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=False,
        comment="积分所有者的内部用户 ID",
    )
    run_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="触发扣费或退款的运行雪花 ID"
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False, comment="积分变更类型")
    delta: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="积分变更数量")
    balance_after: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="本次变更后的积分余额"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="明细创建时间",
    )
