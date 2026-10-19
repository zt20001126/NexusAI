"""提供智能体运行记录的 ORM 持久化及恢复查询。"""

import hashlib

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from agent.errors import DuplicateAgentRunRequest
from agent.enums import AgentType
from agent.schemas.run import RunRecord, RunStatus
from app.db.database import PostgresDatabase
from app.models.conversation import Conversation
from app.models.run import AgentRun
from app.models.user import User
from infra.snowflake import to_database_id


class PostgresRunStore:
    """运行存储适配器，保存状态并恢复 Runner 所需的运行上下文。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享数据库会话工厂。"""
        self._database = database

    def save(self, record: RunRecord) -> None:
        """新增或更新智能体运行状态、元数据和更新时间。"""
        statement = insert(AgentRun).values(
            run_id=to_database_id(record.run_id),
            conversation_id=to_database_id(record.conversation_id),
            status=record.status.value,
            run_metadata=record.metadata,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[AgentRun.run_id],
            set_={
                "conversation_id": statement.excluded.conversation_id,
                "status": statement.excluded.status,
                "metadata": statement.excluded["metadata"],
                "updated_at": func.now(),
            },
        )
        try:
            with self._database.session_factory.begin() as session:
                session.execute(statement)
        except IntegrityError as error:
            if record.metadata.get("request_id"):
                raise DuplicateAgentRunRequest() from error
            raise

    def get(self, run_id: str) -> RunRecord | None:
        """读取运行记录并转换为 Agent 层领域记录。"""
        statement = (
            select(
                AgentRun,
                User.account.label("principal_id"),
                Conversation.agent.label("agent"),
            )
            .join(
                Conversation,
                Conversation.conversation_id == AgentRun.conversation_id,
            )
            .join(User, User.user_id == Conversation.owner_id)
            .where(AgentRun.run_id == to_database_id(run_id))
        )
        with self._database.session_factory() as session:
            row = session.execute(statement).one_or_none()
        if row is None:
            return None

        run, principal_id, agent = row
        return RunRecord(
            run_id=str(run.run_id),
            conversation_id=str(run.conversation_id),
            principal_id=principal_id,
            status=RunStatus(run.status),
            metadata=dict(run.run_metadata or {}),
            agent=AgentType(agent),
        )

    def get_by_request_id(self, request_id: str, principal_id: str) -> RunRecord | None:
        """读取幂等请求已绑定的运行，并同时按可信主体过滤。"""
        statement = (
            select(AgentRun.run_id)
            .join(Conversation, Conversation.conversation_id == AgentRun.conversation_id)
            .join(User, User.user_id == Conversation.owner_id)
            .where(
                User.account == principal_id,
                AgentRun.run_metadata["request_key"].astext
                == hashlib.sha256(f"{principal_id}:{request_id}".encode("utf-8")).hexdigest(),
            )
            .limit(1)
        )
        with self._database.session_factory() as session:
            database_run_id = session.scalar(statement)
        return self.get(str(database_run_id)) if database_run_id is not None else None

    def list_active(self, principal_id: str) -> list[RunRecord]:
        """按主体读取最新的排队及执行中运行，排除等待回答和终态。"""
        statement = (
            select(AgentRun.run_id)
            .join(Conversation, Conversation.conversation_id == AgentRun.conversation_id)
            .join(User, User.user_id == Conversation.owner_id)
            .where(User.account == principal_id, AgentRun.status.in_(["queued", "running"]))
            .order_by(AgentRun.updated_at.desc(), AgentRun.run_id.desc())
        )
        with self._database.session_factory() as session:
            run_ids = session.scalars(statement).all()
        return [record for run_id in run_ids if (record := self.get(str(run_id))) is not None]

    def claim(self, run_id: str) -> bool:
        """以单条条件更新原子声明排队运行，避免 Celery 重复投递重复执行。"""
        statement = (
            update(AgentRun)
            .where(
                AgentRun.run_id == to_database_id(run_id),
                AgentRun.status == "queued",
            )
            .values(status="running", updated_at=func.now())
            .returning(AgentRun.run_id)
        )
        with self._database.session_factory.begin() as session:
            return session.scalar(statement) is not None

    def get_latest_for_conversation(
        self, conversation_id: str, principal_id: str
    ) -> RunRecord | None:
        """从指定主体的会话中读取最近更新的运行。"""
        statement = (
            select(AgentRun.run_id)
            .join(Conversation, Conversation.conversation_id == AgentRun.conversation_id)
            .join(User, User.user_id == Conversation.owner_id)
            .where(
                AgentRun.conversation_id == to_database_id(conversation_id),
                User.account == principal_id,
            )
            .order_by(AgentRun.updated_at.desc(), AgentRun.run_id.desc())
            .limit(1)
        )
        with self._database.session_factory() as session:
            database_run_id = session.scalar(statement)
        return self.get(str(database_run_id)) if database_run_id is not None else None
