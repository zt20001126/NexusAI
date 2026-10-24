"""在同一 PostgreSQL 事务中保存新对话并完成积分扣费。"""

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from agent.errors import AgentRunRequestConflictError, InsufficientCreditsError
from agent.errors import ConversationAccessDeniedError
from agent.enums import AgentType
from agent.schemas.run import RunRecord, RunStatus
from app.credit_constants import CHAT_MESSAGE_CREDIT_COST, CREDIT_EVENT_MESSAGE_DEBIT
from app.crud.identity import resolve_user_id
from app.db.database import PostgresDatabase
from app.models.conversation import Conversation
from app.models.credit import CreditEntry, UserCredit
from app.models.message import Message
from app.models.run import AgentRun
from app.models.user import User
from infra.snowflake import to_database_id


class PostgresBilledChatSubmissionStore:
    """原子写入新运行、用户消息、积分扣费和扣费明细。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享数据库和雪花 ID 生成器。"""
        self._database = database

    def submit(
        self,
        record: RunRecord,
        message_id: str,
        user_content: dict,
    ) -> tuple[RunRecord, int, int]:
        """检查幂等请求并原子受理，返回运行及事务提交后的余额版本。"""
        if not record.metadata.get("request_key"):
            raise ValueError("计费对话必须提供 request_id")
        database_conversation_id = to_database_id(record.conversation_id)
        database_run_id = to_database_id(record.run_id)
        database_message_id = to_database_id(message_id)
        request_key = record.metadata["request_key"]

        try:
            with self._database.session_factory.begin() as session:
                user_id = resolve_user_id(
                    session,
                    record.principal_id,
                    create=True,
                    id_generator=self._database.id_generator,
                )
                credit = session.scalar(
                    select(UserCredit)
                    .where(UserCredit.user_id == user_id)
                    .with_for_update()
                )
                if credit is None:
                    raise RuntimeError("积分余额记录不存在")

                # 同一用户的提交在余额行锁处串行；锁后查询可见并发请求刚提交的运行。
                existing = session.scalar(
                    select(AgentRun).where(
                        AgentRun.run_metadata["request_key"].astext == request_key
                    )
                )
                if existing is not None:
                    if existing.run_metadata.get("request_hash") != record.metadata.get("request_hash"):
                        raise AgentRunRequestConflictError()
                    return self._to_record(session, existing), credit.balance, credit.version

                if credit.balance < CHAT_MESSAGE_CREDIT_COST:
                    raise InsufficientCreditsError()

                conversation = session.scalar(
                    select(Conversation)
                    .where(Conversation.conversation_id == database_conversation_id)
                    .with_for_update()
                )
                if conversation is None:
                    session.add(
                        Conversation(
                            conversation_id=database_conversation_id,
                            owner_id=user_id,
                            agent=record.agent.value,
                        )
                    )
                elif conversation.owner_id != user_id or conversation.agent != record.agent.value:
                    raise ConversationAccessDeniedError()

                session.add(
                    Message(
                        message_id=database_message_id,
                        conversation_id=database_conversation_id,
                        role="user",
                        content=user_content,
                    )
                )
                session.add(
                    AgentRun(
                        run_id=database_run_id,
                        conversation_id=database_conversation_id,
                        status=record.status.value,
                        run_metadata=record.metadata,
                    )
                )
                session.execute(
                    update(Conversation)
                    .where(Conversation.conversation_id == database_conversation_id)
                    .values(updated_at=func.now())
                )
                credit.balance -= CHAT_MESSAGE_CREDIT_COST
                credit.version += 1
                session.add(
                    CreditEntry(
                        event_key=f"debit:{database_run_id}",
                        user_id=user_id,
                        run_id=database_run_id,
                        kind=CREDIT_EVENT_MESSAGE_DEBIT,
                        delta=-CHAT_MESSAGE_CREDIT_COST,
                        balance_after=credit.balance,
                    )
                )
                session.flush()
                balance, version = credit.balance, credit.version
            return record, balance, version
        except IntegrityError as error:
            # 相同 request_key 竞争失败时复用胜出的提交；其它完整性错误继续上抛。
            existing = self._find_existing(record)
            if existing is None:
                raise
            if existing.metadata.get("request_hash") != record.metadata.get("request_hash"):
                raise AgentRunRequestConflictError() from error
            balance, version = self._credit_snapshot(record.principal_id)
            return existing, balance, version

    def _find_existing(self, record: RunRecord) -> RunRecord | None:
        with self._database.session_factory() as session:
            run = session.scalar(
                select(AgentRun).where(
                    AgentRun.run_metadata["request_key"].astext
                    == record.metadata.get("request_key")
                )
            )
            return self._to_record(session, run) if run is not None else None

    def _credit_snapshot(self, principal_id: str) -> tuple[int, int]:
        with self._database.session_factory() as session:
            row = session.execute(
                select(UserCredit.balance, UserCredit.version)
                .join(User, User.user_id == UserCredit.user_id)
                .where(User.account == principal_id)
            ).one()
        return row.balance, row.version

    @staticmethod
    def _to_record(session, run: AgentRun) -> RunRecord:
        """将已存在幂等运行映射回 Runner 领域记录。"""
        conversation = session.get(Conversation, run.conversation_id)
        user = session.get(User, conversation.owner_id) if conversation else None
        if conversation is None or user is None:
            raise RuntimeError("幂等运行缺少所属会话")
        return RunRecord(
            run_id=str(run.run_id),
            conversation_id=str(run.conversation_id),
            principal_id=user.account,
            status=RunStatus(run.status),
            metadata=dict(run.run_metadata or {}),
            agent=AgentType(conversation.agent),
        )
