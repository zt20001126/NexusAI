"""复用现有 users 表持久化邮箱账号凭据。"""

from dataclasses import dataclass
from sqlalchemy import select

from app.credit_constants import (
    CREDIT_EVENT_REGISTRATION_GRANT,
    REGISTRATION_CREDIT_GRANT,
)
from app.db.database import PostgresDatabase
from app.models.credit import CreditEntry, UserCredit
from app.models.user import User


@dataclass(frozen=True)
class AuthUser:
    """与 SQLAlchemy Session 生命周期隔离的账号凭据。"""

    user_id: int
    account: str
    password_hash: str | None


class PostgresAuthRepository:
    """只读取和更新已有 users 表，不创建独立认证表。"""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def get_user(self, email: str) -> AuthUser | None:
        """按规范化邮箱读取现有账号和密码哈希。"""
        with self._database.session_factory() as session:
            row = session.scalar(select(User).where(User.account == email))
            return _to_auth_user(row) if row is not None else None

    def create_user(self, email: str, password_hash: str) -> bool:
        """在事务锁内创建邮箱账号，防止重复注册竞争。"""
        with self._database.session_factory.begin() as session:
            _lock_email(session, email)
            existing_id = session.scalar(
                select(User.user_id).where(User.account == email)
            )
            if existing_id is not None:
                return False
            user_id = self._database.id_generator.next_id()
            session.add(
                User(
                    user_id=user_id,
                    account=email,
                    password_hash=password_hash,
                )
            )
            session.add(
                UserCredit(
                    user_id=user_id,
                    balance=REGISTRATION_CREDIT_GRANT,
                    version=1,
                )
            )
            session.add(
                CreditEntry(
                    event_key=f"grant:{user_id}",
                    user_id=user_id,
                    run_id=None,
                    kind=CREDIT_EVENT_REGISTRATION_GRANT,
                    delta=REGISTRATION_CREDIT_GRANT,
                    balance_after=REGISTRATION_CREDIT_GRANT,
                )
            )
            return True

    def update_password(self, email: str, password_hash: str) -> bool:
        """更新现有邮箱账号密码；当前 users 模型不单独记录认证会话。"""
        with self._database.session_factory.begin() as session:
            user = session.scalar(
                select(User).where(User.account == email).with_for_update()
            )
            if user is None:
                return False
            user.password_hash = password_hash
            return True


def _lock_email(session, email: str) -> None:
    """通过 PostgreSQL 事务锁串行化相同邮箱的账号创建。"""
    from sqlalchemy import func, select

    session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(email, 0)))
    )


def _to_auth_user(row: User) -> AuthUser:
    """复制用户凭据字段，避免向业务层泄露 ORM 实体。"""
    return AuthUser(row.user_id, row.account, row.password_hash)
