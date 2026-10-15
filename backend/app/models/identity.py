"""定义认证主体到内部用户标识的数据库映射模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserIdentity(Base):
    """用户身份模型，用于将可信外部主体映射到内部雪花用户 ID。"""

    __tablename__ = "user_identities"
    __table_args__ = {"comment": "可信外部主体与内部雪花用户 ID 的映射"}

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        comment="内部雪花用户 ID",
    )
    external_principal: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, comment="认证系统提供的可信主体标识"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="身份映射创建时间",
    )
