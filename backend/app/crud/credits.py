"""提供积分余额、明细、退款和终态对账的事务仓储。"""

from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import aliased

from app.credit_constants import (
    CHAT_MESSAGE_CREDIT_COST,
    CREDIT_EVENT_MESSAGE_DEBIT,
    CREDIT_EVENT_RUN_REFUND,
)
from app.db.database import PostgresDatabase
from app.models.credit import CreditEntry, UserCredit
from app.models.user import User


@dataclass(frozen=True)
class CreditBalanceSnapshot:
    """服务层使用的积分余额和缓存版本，不暴露 ORM 实体。"""

    principal_id: str
    user_id: int
    balance: int
    version: int


class PostgresCreditRepository:
    """负责积分余额读取、退款与终态未退款记录核对。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享 PostgreSQL Session 工厂。"""
        self._database = database

    def get_snapshot(self, principal_id: str) -> CreditBalanceSnapshot | None:
        """按可信账号读取当前余额，供会话接口和缓存回填使用。"""
        statement = (
            select(User.user_id, User.account, UserCredit.balance, UserCredit.version)
            .join(UserCredit, UserCredit.user_id == User.user_id)
            .where(User.account == principal_id)
        )
        with self._database.session_factory() as session:
            row = session.execute(statement).one_or_none()
        if row is None:
            return None
        return CreditBalanceSnapshot(row.account, row.user_id, row.balance, row.version)

    def list_snapshots(
        self, after_user_id: int, limit: int
    ) -> list[CreditBalanceSnapshot]:
        """按用户 ID 游标分页返回全量余额，避免启动时一次性载入所有账号。"""
        statement = (
            select(User.user_id, User.account, UserCredit.balance, UserCredit.version)
            .join(UserCredit, UserCredit.user_id == User.user_id)
            .where(User.user_id > after_user_id)
            .order_by(User.user_id)
            .limit(limit)
        )
        with self._database.session_factory() as session:
            rows = session.execute(statement).all()
        return [
            CreditBalanceSnapshot(row.account, row.user_id, row.balance, row.version)
            for row in rows
        ]

    def refund_run(self, run_id: str) -> CreditBalanceSnapshot | None:
        """按 run_id 幂等退款；重复调用返回当前余额但不会重复增加积分。"""
        database_run_id = int(run_id)
        with self._database.session_factory.begin() as session:
            debit = session.scalar(
                select(CreditEntry).where(
                    CreditEntry.run_id == database_run_id,
                    CreditEntry.kind == CREDIT_EVENT_MESSAGE_DEBIT,
                )
            )
            if debit is None:
                return None
            credit = session.scalar(
                select(UserCredit)
                .where(UserCredit.user_id == debit.user_id)
                .with_for_update()
            )
            if credit is None:
                raise RuntimeError("积分余额记录不存在")
            refund_key = f"refund:{database_run_id}"
            if session.get(CreditEntry, refund_key) is None:
                credit.balance += CHAT_MESSAGE_CREDIT_COST
                credit.version += 1
                session.add(
                    CreditEntry(
                        event_key=refund_key,
                        user_id=credit.user_id,
                        run_id=database_run_id,
                        kind=CREDIT_EVENT_RUN_REFUND,
                        delta=CHAT_MESSAGE_CREDIT_COST,
                        balance_after=credit.balance,
                    )
                )
            user = session.get(User, credit.user_id)
            if user is None:
                raise RuntimeError("积分所属用户不存在")
            return CreditBalanceSnapshot(
                principal_id=user.account,
                user_id=credit.user_id,
                balance=credit.balance,
                version=credit.version,
            )

    def refund_terminal_runs(self, batch_size: int = 500) -> list[CreditBalanceSnapshot]:
        """补退所有已持久化为 failed/cancelled 但尚无退款明细的运行。"""
        from app.models.conversation import Conversation
        from app.models.run import AgentRun

        refund_entry = aliased(CreditEntry)
        missing_refund = ~exists(
            select(refund_entry.event_key).where(
                refund_entry.run_id == AgentRun.run_id,
                refund_entry.kind == CREDIT_EVENT_RUN_REFUND,
            )
        )
        statement = (
            select(AgentRun.run_id)
            .join(Conversation, Conversation.conversation_id == AgentRun.conversation_id)
            .join(
                CreditEntry,
                (CreditEntry.run_id == AgentRun.run_id)
                & (CreditEntry.kind == CREDIT_EVENT_MESSAGE_DEBIT),
            )
            .where(AgentRun.status.in_(["failed", "cancelled"]), missing_refund)
            .order_by(AgentRun.run_id)
            .limit(batch_size)
        )
        with self._database.session_factory() as session:
            run_ids = [str(run_id) for run_id in session.scalars(statement).all()]
        snapshots = []
        for run_id in run_ids:
            snapshot = self.refund_run(run_id)
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots
