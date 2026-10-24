"""定义 Stripe 积分充值尝试的持久化模型。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CreditTopUp(Base):
    """保存一次充值尝试及其 Stripe Checkout Session 关联。"""

    __tablename__ = "credit_topups"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_credit_topups_user_request"),
        UniqueConstraint("stripe_session_id", name="uq_credit_topups_stripe_session"),
        CheckConstraint("amount > 0", name="ck_credit_topups_amount_positive"),
        CheckConstraint(
            "stripe_amount > 0", name="ck_credit_topups_stripe_amount_positive"
        ),
        CheckConstraint(
            "status IN ('pending', 'paid', 'failed', 'expired')",
            name="ck_credit_topups_status",
        ),
        CheckConstraint("currency ~ '^[a-z]{3}$'", name="ck_credit_topups_currency"),
        Index("idx_credit_topups_user_created", "user_id", "created_at"),
        {"comment": "积分充值尝试"},
    )

    top_up_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False, comment="充值尝试雪花 ID"
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        comment="充值所属用户 ID",
    )
    request_id: Mapped[str] = mapped_column(Text, nullable=False, comment="客户端幂等键")
    currency: Mapped[str] = mapped_column(Text, nullable=False, comment="Stripe ISO 4217 币种")
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="充值金额主单位")
    stripe_amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="Stripe 币种最小单位金额"
    )
    stripe_session_id: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Stripe Checkout Session ID"
    )
    checkout_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Stripe Checkout 跳转地址"
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'"), comment="充值尝试状态"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
