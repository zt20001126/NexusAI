"""提供充值尝试的 PostgreSQL 幂等仓储。"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.credit_constants import CREDIT_EVENT_TOP_UP, MAX_CREDIT_BALANCE
from app.crud.credits import CreditBalanceSnapshot
from app.db.database import PostgresDatabase
from app.models.credit import CreditEntry, UserCredit
from app.models.topup import CreditTopUp
from app.models.user import User
from infra.snowflake import to_database_id


@dataclass(frozen=True)
class CreditTopUpRecord:
    """服务层使用的充值尝试视图。"""

    top_up_id: str
    user_id: int
    principal_id: str
    request_id: str
    currency: str
    amount: int
    stripe_amount: int
    stripe_session_id: str | None
    checkout_url: str | None
    status: str


class PostgresCreditTopUpRepository:
    """管理充值请求、Stripe 关联和原子积分到账。"""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def create_or_get(
        self,
        principal_id: str,
        request_id: str,
        currency: str,
        amount: int,
        stripe_amount: int,
    ) -> tuple[CreditTopUpRecord, bool]:
        """按可信主体和请求键创建或读取充值尝试。"""
        try:
            with self._database.session_factory.begin() as session:
                user = session.scalar(select(User).where(User.account == principal_id))
                if user is None:
                    raise LookupError("积分账号不存在")
                existing = session.scalar(
                    select(CreditTopUp).where(
                        CreditTopUp.user_id == user.user_id,
                        CreditTopUp.request_id == request_id,
                    )
                )
                if existing is not None:
                    return self._to_record(existing, principal_id), False
                if session.get(UserCredit, user.user_id) is None:
                    raise LookupError("积分余额记录不存在")
                top_up = CreditTopUp(
                    top_up_id=self._database.id_generator.next_id(),
                    user_id=user.user_id,
                    request_id=request_id,
                    currency=currency,
                    amount=amount,
                    stripe_amount=stripe_amount,
                )
                session.add(top_up)
                session.flush()
                return self._to_record(top_up, principal_id), True
        except IntegrityError:
            with self._database.session_factory() as session:
                user_id = session.scalar(
                    select(User.user_id).where(User.account == principal_id)
                )
                existing = session.scalar(
                    select(CreditTopUp).where(
                        CreditTopUp.user_id == user_id,
                        CreditTopUp.request_id == request_id,
                    )
                )
                if existing is None:
                    raise
                return self._to_record(existing, principal_id), False

    def attach_checkout(
        self,
        top_up_id: str,
        session_id: str,
        checkout_url: str,
    ) -> CreditTopUpRecord:
        """保存 Stripe Session；重复绑定同一 Session 可安全重试。"""
        with self._database.session_factory.begin() as session:
            top_up = session.scalar(
                select(CreditTopUp)
                .where(CreditTopUp.top_up_id == to_database_id(top_up_id))
                .with_for_update()
            )
            if top_up is None:
                raise LookupError("充值尝试不存在")
            if top_up.stripe_session_id not in (None, session_id):
                raise RuntimeError("充值尝试已绑定其他支付会话")
            top_up.stripe_session_id = session_id
            top_up.checkout_url = checkout_url
            principal_id = session.scalar(
                select(User.account).where(User.user_id == top_up.user_id)
            )
            if principal_id is None:
                raise LookupError("充值账号不存在")
            return self._to_record(top_up, principal_id)

    def get_for_user(
        self, principal_id: str, top_up_id: str
    ) -> CreditTopUpRecord | None:
        """只读取当前可信账号拥有的充值尝试。"""
        statement = (
            select(CreditTopUp, User.account)
            .join(User, User.user_id == CreditTopUp.user_id)
            .where(
                User.account == principal_id,
                CreditTopUp.top_up_id == to_database_id(top_up_id),
            )
        )
        with self._database.session_factory() as session:
            row = session.execute(statement).one_or_none()
        if row is None:
            return None
        return self._to_record(row[0], row[1])

    def apply_payment_event(
        self,
        *,
        top_up_id: str,
        session_id: str,
        currency: str,
        stripe_amount: int,
        status: str,
    ) -> CreditBalanceSnapshot | None:
        """核对支付字段并原子更新状态、余额及唯一充值明细。"""
        with self._database.session_factory.begin() as session:
            top_up = session.scalar(
                select(CreditTopUp)
                .where(CreditTopUp.top_up_id == to_database_id(top_up_id))
                .with_for_update()
            )
            if top_up is None:
                return None
            if (
                top_up.currency != currency
                or top_up.stripe_amount != stripe_amount
                or top_up.stripe_session_id not in (None, session_id)
            ):
                raise ValueError("Stripe 支付信息与充值请求不匹配")

            if top_up.stripe_session_id is None:
                top_up.stripe_session_id = session_id
            if status in {"failed", "expired"}:
                if top_up.status != "paid":
                    top_up.status = status
                return None
            if status != "paid":
                return None
            if top_up.status == "paid":
                return self._get_snapshot(session, top_up.user_id)

            credit = session.scalar(
                select(UserCredit)
                .where(UserCredit.user_id == top_up.user_id)
                .with_for_update()
            )
            if credit is None:
                raise LookupError("积分余额记录不存在")

            event_key = f"top_up:{top_up.top_up_id}"
            entry = session.get(CreditEntry, event_key)
            if entry is None:
                if credit.balance > MAX_CREDIT_BALANCE - top_up.amount:
                    raise OverflowError("充值后积分余额超出数据库整数范围")
                credit.balance += top_up.amount
                credit.version += 1
                session.add(
                    CreditEntry(
                        event_key=event_key,
                        user_id=top_up.user_id,
                        kind=CREDIT_EVENT_TOP_UP,
                        delta=top_up.amount,
                        balance_after=credit.balance,
                    )
                )
            top_up.status = "paid"
            user = session.get(User, top_up.user_id)
            if user is None:
                raise LookupError("充值账号不存在")
            return CreditBalanceSnapshot(
                principal_id=user.account,
                user_id=user.user_id,
                balance=credit.balance,
                version=credit.version,
            )

    @staticmethod
    def _get_snapshot(session, user_id: int) -> CreditBalanceSnapshot:
        row = session.execute(
            select(User.account, UserCredit.balance, UserCredit.version)
            .join(UserCredit, UserCredit.user_id == User.user_id)
            .where(User.user_id == user_id)
        ).one()
        return CreditBalanceSnapshot(row.account, user_id, row.balance, row.version)

    @staticmethod
    def _to_record(top_up: CreditTopUp, principal_id: str) -> CreditTopUpRecord:
        return CreditTopUpRecord(
            top_up_id=str(top_up.top_up_id),
            user_id=top_up.user_id,
            principal_id=principal_id,
            request_id=top_up.request_id,
            currency=top_up.currency,
            amount=top_up.amount,
            stripe_amount=top_up.stripe_amount,
            stripe_session_id=top_up.stripe_session_id,
            checkout_url=top_up.checkout_url,
            status=top_up.status,
        )
