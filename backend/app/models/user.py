"""定义应用用户及其本地账号信息模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    """用户模型；账号列同时承接当前认证主体的稳定映射值。"""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        {"comment": "用户账号与角色"},
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        comment="内部雪花用户 ID",
    )
    account: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, comment="唯一账号"
    )
    password_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="密码哈希；迁移的旧账号尚未设置密码时为空"
    )
    role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'user'"),
        comment="用户角色：user 或 admin",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="账号创建时间",
    )
